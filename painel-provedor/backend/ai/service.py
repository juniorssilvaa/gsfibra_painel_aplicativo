"""
Orquestrador de IA do NIO HUB.

Prompt Base + Tools (Registry/Executor) + Providers + Redis memory.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from datetime import timezone as dt_timezone
from typing import Any, Dict, List, Optional

from asgiref.sync import async_to_sync, sync_to_async
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ai.audit import ToolCallLog, log_llm_decision, log_turn_end, log_turn_start, log_usage
from ai.context import build_full_context_blocks
from ai.definitions.tool_definitions import build_tools_for_provedor
from ai.executor.tool_executor import ToolExecutor
from ai.learnings import learnings_system_message
from ai.memory import normalize_phone_number, redis_memory_service
from core.redis_memory_service import CONTEXT_MAX_MESSAGES
from ai.prompt_base import build_system_prompt
from ai.providers.config import (
    AI_PROVIDERS,
    OPENAI_KEY_MISSING_MSG,
    get_provedor_ai_model,
    get_provedor_ai_provider,
    get_provedor_openai_api_key,
    get_provedor_openai_model,
)
from ai.providers import get_provider_client
from ai.response_formatter import AIResponseFormatter
from ai.tools.integrations import AIActionsHandler
from core.horario_utils import verificar_automacao_agendada
from core.models import Provedor

logger = logging.getLogger(__name__)

ESPERA_CHECK_PROMPT = (
    "Você revisa respostas de um agente virtual de atendimento. O agente só consegue agir enquanto escreve "
    "a resposta; depois de enviá-la, só volta a agir quando o cliente mandar outra mensagem.\n"
    "Pergunta: a resposta do agente deixa o cliente esperando por algo que o próprio agente disse que vai "
    "fazer, verificar, consultar, enviar ou retornar depois, sem entregar isso agora?\n"
    "NÃO conta: pedir um dado ao cliente, fazer uma pergunta, informar um resultado, ou dizer que algo foi "
    "feito quando a ferramenta correspondente aparece como executada.\n"
    "Responda só SIM ou NAO."
)

ESPERA_CORRECAO_MSG = (
    "Sua resposta acima NAO foi enviada ao cliente: ela promete verificar ou fazer algo depois, mas voce nao "
    "tem 'depois' (so volta a agir quando o cliente escrever de novo). Faca agora, nesta resposta: chame a "
    "ferramenta que resolve o pedido e responda com o resultado; se faltar um dado do cliente, peca o dado; "
    "se nenhuma ferramenta resolve, diga com clareza o que voce pode fazer. Nao diga 'um momento' nem 'vou verificar'."
)


def _repete_dados_contrato(texto: str, conversation_state: Dict[str, Any]) -> bool:
    """True se a resposta mostra de novo o id ou o logradouro de algum contrato já apresentado."""
    if not texto:
        return False
    texto_digitos = re.sub(r"[^\d]", " ", texto)
    texto_lower = texto.lower()
    for contrato in conversation_state.get("contratos") or []:
        if not isinstance(contrato, dict):
            continue
        cid = re.sub(
            r"[^\d]",
            "",
            str(contrato.get("contratoId") or contrato.get("contrato_id") or contrato.get("contrato") or ""),
        )
        if len(cid) >= 3 and re.search(rf"(?<!\d){cid}(?!\d)", texto_digitos):
            return True
        logradouro = str(contrato.get("endereco_logradouro") or "").strip().lower()
        if len(logradouro) >= 8 and logradouro in texto_lower:
            return True
    return False


def _filter_ai_context_by_visible_cutoff(history_items, conversation):
    if not conversation or not history_items:
        return history_items
    cutoff_iso = (getattr(conversation, "additional_attributes", None) or {}).get(
        "agent_chat_visible_from"
    )
    if not cutoff_iso:
        return history_items
    dt_cut = parse_datetime(str(cutoff_iso).replace("Z", "+00:00"))
    if not dt_cut:
        return history_items
    if timezone.is_naive(dt_cut):
        dt_cut = timezone.make_aware(dt_cut, timezone.get_current_timezone())
    dt_cut_utc = dt_cut.astimezone(dt_timezone.utc)

    def _item_time(item):
        ts = item.get("timestamp")
        if not ts:
            return None
        try:
            dt = parse_datetime(str(ts).replace("Z", "+00:00"))
            if dt and timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except Exception:
            return None

    filtered = []
    for item in history_items:
        t = _item_time(item)
        if t is None:
            continue
        if t >= dt_cut_utc:
            filtered.append(item)
    return filtered


class AIService:
    """Motor de IA: Prompt Base + Tools + multi-provider."""

    def __init__(self):
        self.max_tokens = 512
        self.temperature = 0.5
        self.actions = AIActionsHandler(openai_service=self)
        self.formatter = AIResponseFormatter(openai_service=self)
        self.executor = ToolExecutor(actions_handler=self.actions)

    def _determinar_genero_nome(self, nome: str) -> str:
        return self.formatter._determinar_genero_nome(nome)

    def _get_greeting_time(self) -> str:
        now = timezone.localtime(timezone.now())
        hour = now.hour
        if 5 <= hour < 12:
            return "bom dia"
        if 12 <= hour < 18:
            return "boa tarde"
        return "boa noite"

    def _formatar_horarios_atendimento(self, horarios: list) -> str:
        return self.actions._formatar_horarios_atendimento(horarios)

    def _client_for(self, provedor: Provedor):
        provider = get_provider_client(provedor)
        return provider.client() if provider.available else None

    @staticmethod
    def _agent_mode(provedor: Provedor) -> str:
        return (getattr(provedor, "agent_mode", None) or "isp").strip().lower()

    def _build_system_prompt(self, provedor: Provedor, contexto: Dict[str, Any] = None) -> str:
        return build_system_prompt(provedor, contexto, openai_service=self)

    def _build_tools(self, provedor: Provedor) -> List[Dict[str, Any]]:
        return build_tools_for_provedor(provedor)

    async def _deixa_cliente_esperando(
        self, client, model: str, mensagem: str, resposta: str, tools_executadas: List[str]
    ) -> bool:
        """A própria IA avalia se a resposta promete uma ação que não vai acontecer."""
        if not resposta:
            return False
        executadas = ", ".join(tools_executadas) or "nenhuma"
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=[
                    {"role": "system", "content": ESPERA_CHECK_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Mensagem do cliente: {mensagem[:1000]}\n"
                            f"Ferramentas executadas nesta resposta: {executadas}\n"
                            f"Resposta do agente: {resposta[:1500]}"
                        ),
                    },
                ],
                temperature=0,
                max_tokens=3,
            )
            veredito = (response.choices[0].message.content or "").strip().upper()
            return veredito.startswith("SIM")
        except Exception:
            logger.debug("[AI] Falha na checagem de resposta em espera", exc_info=True)
            return False

    async def generate_response(
        self,
        mensagem: str,
        provedor: Provedor,
        contexto: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        conversation_id = None
        contact_phone = "unknown"
        channel = "wa"

        try:
            bot_mode = await sync_to_async(
                lambda: Provedor.objects.filter(pk=provedor.id).values_list("bot_mode", flat=True).first()
            )()
        except Exception:
            bot_mode = getattr(provedor, "bot_mode", None)
        bot_mode = (bot_mode or getattr(provedor, "bot_mode", None) or "ia").strip().lower()
        if bot_mode != "ia":
            return {
                "success": False,
                "motivo": "BOT_MODE_NOT_IA",
                "erro": "Modo do provedor não é IA (definido pelo superadmin).",
            }

        automacao_info = await sync_to_async(verificar_automacao_agendada)(provedor)
        if not automacao_info.get("ativa", True):
            return {
                "success": False,
                "motivo": "AUTOMATION_SCHEDULE_OFF",
                "erro": "Automação da IA indisponível neste horário.",
                "horario_info": automacao_info.get("horario_info"),
            }

        if contexto and contexto.get("conversation"):
            conversation_id = contexto["conversation"].id
        if contexto and contexto.get("contact"):
            contact_phone = contexto["contact"].phone
        elif contexto and contexto.get("contact_phone"):
            contact_phone = contexto["contact_phone"]
        if contexto and contexto.get("canal"):
            channel = redis_memory_service.normalize_channel(contexto["canal"])

        if not conversation_id:
            return {"success": False, "erro": "ID da conversa não identificado no contexto."}

        if contact_phone and contact_phone != "unknown":
            await redis_memory_service.migrate_unknown_phone(
                provedor.id, conversation_id, channel, contact_phone
            )

        lock_acquired = await redis_memory_service.acquire_lock(
            provedor.id, conversation_id, channel, contact_phone
        )
        if not lock_acquired:
            return {"success": False, "motivo": "IA_BUSY"}

        try:
            await redis_memory_service.update_ai_state(
                provedor.id, conversation_id, {"locked": True}, channel, contact_phone
            )

            client = self._client_for(provedor)
            if not client:
                return {"success": False, "erro": OPENAI_KEY_MISSING_MSG}

            model = get_provedor_openai_model(provedor)
            ch_norm = redis_memory_service.normalize_channel(channel)
            ph_norm = normalize_phone_number(contact_phone)
            ai_conversation_id = f"ai:{provedor.id}:{ch_norm}:{conversation_id}:{ph_norm}"

            mem = await redis_memory_service.get_ai_memory(
                provedor.id, conversation_id, channel, contact_phone
            )
            conversation_state = mem["state"]
            history_items = (mem.get("context") or [])[-CONTEXT_MAX_MESSAGES:]

            conv_for_cutoff = None
            if contexto and contexto.get("conversation"):
                try:
                    from conversations.models import Conversation as ConvModel

                    conv_for_cutoff = await sync_to_async(ConvModel.objects.get)(pk=conversation_id)
                except Exception:
                    conv_for_cutoff = contexto.get("conversation")
                history_items = _filter_ai_context_by_visible_cutoff(history_items, conv_for_cutoff)

            has_ai_interaction = any(msg.get("role") == "assistant" for msg in history_items)

            messages: List[Dict[str, Any]] = []
            for msg_data in history_items:
                role = msg_data.get("role")
                content = (msg_data.get("content") or "").strip()
                if not content:
                    continue
                if role in ("user", "assistant"):
                    messages.append({"role": role, "content": content})

            base_system_prompt = await sync_to_async(self._build_system_prompt)(provedor, contexto)
            context_blocks = build_full_context_blocks(
                provedor=provedor,
                conversation_state=conversation_state,
                conversation_id=conversation_id,
                contact_phone=contact_phone,
                channel=channel,
                ai_conversation_id=ai_conversation_id,
                has_ai_interaction=has_ai_interaction,
                conversation=conv_for_cutoff,
            )
            system_prompt = f"{base_system_prompt}\n\n{context_blocks}"

            tools = self._build_tools(provedor)
            tool_names = [
                (t.get("function") or {}).get("name")
                for t in (tools or [])
                if (t.get("function") or {}).get("name")
            ]
            provider_name = get_provedor_ai_provider(provedor)
            log_turn_start(
                provedor_id=provedor.id,
                conversation_id=conversation_id,
                channel=channel,
                phone=contact_phone,
                mensagem=mensagem,
                model=model,
                provider=provider_name,
                tool_names=tool_names,
            )

            chat_messages = [{"role": "system", "content": system_prompt}] + messages
            if (
                not chat_messages
                or chat_messages[-1].get("role") != "user"
                or chat_messages[-1].get("content") != mensagem
            ):
                chat_messages.append({"role": "user", "content": mensagem})

            try:
                learnings_msg = await sync_to_async(learnings_system_message)(provedor.id, mensagem)
                if not learnings_msg:
                    previous_user = next(
                        (
                            m["content"]
                            for m in reversed(messages)
                            if m.get("role") == "user" and m.get("content") != mensagem
                        ),
                        "",
                    )
                    if previous_user:
                        learnings_msg = await sync_to_async(learnings_system_message)(
                            provedor.id, f"{mensagem}\n{previous_user}"
                        )
                if learnings_msg:
                    chat_messages.append({"role": "system", "content": learnings_msg})
            except Exception:
                logger.exception("[AI] Falha ao buscar aprendizados do provedor %s", provedor.id)

            if self._agent_mode(provedor) != "support" and conversation_state.get("contrato_escolhido"):
                chat_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Os dados do cadastro/contrato JA foram confirmados nesta conversa "
                            "(Redis: contrato_escolhido=true). "
                            "NUNCA peca o cliente confirmar nome, contrato ou endereco de novo. "
                            "Prossiga com a acao pedida (fatura, suporte, Wi-Fi, etc.)."
                        ),
                    }
                )
            elif self._agent_mode(provedor) != "support" and conversation_state.get(
                "precisa_escolher_contrato"
            ) and not conversation_state.get("contrato_escolhido"):
                if conversation_state.get("confirmacao_pedida"):
                    conteudo_escolha = (
                        "Voce JA perguntou para qual contrato e o atendimento e a lista ja foi mostrada. "
                        "A mensagem atual do cliente e a resposta a essa pergunta. "
                        "NAO liste os contratos de novo. "
                        "Se ele indicou um contrato (numero da lista, id ou endereco), chame selecionar_contrato AGORA "
                        "e ja execute o pedido. Se ele disse outra coisa, responda ao que ele disse."
                    )
                else:
                    conteudo_escolha = (
                        "Os dados do cadastro JA foram confirmados (dados_confirmados). "
                        "NAO peca confirmar nome/endereco de novo. "
                        "Pergunte com naturalidade para qual contrato e este atendimento "
                        "(numero da lista ou id). "
                        "Se o cliente acabou de escolher, chame selecionar_contrato AGORA e ja execute o pedido."
                    )
                chat_messages.append({"role": "system", "content": conteudo_escolha})
            elif self._agent_mode(provedor) != "support" and conversation_state.get(
                "precisa_confirmar_dados"
            ) and not conversation_state.get("contrato_escolhido"):
                if conversation_state.get("confirmacao_pedida"):
                    conteudo_confirmacao = (
                        "Voce JA mostrou os dados do cadastro/contrato e JA perguntou se estao corretos. "
                        "A mensagem atual do cliente e a resposta a essa pergunta. "
                        "NAO mostre os dados de novo e NAO pergunte de novo. "
                        "Se ele confirmou, chame selecionar_contrato AGORA com escolha='sim' "
                        "(ou o contrato que ele indicou) e ja execute o pedido dele. "
                        "Se ele disse que os dados estao errados, peca o CPF/CNPJ correto. "
                        "Se ele falou de outro assunto, responda ao que ele disse."
                    )
                else:
                    conteudo_confirmacao = (
                        "O cliente ja foi consultado no ERP e os dados ainda nao foram confirmados. "
                        "Mostre os dados reais retornados (contratos e enderecos) com naturalidade "
                        "e peca UMA vez se estao corretos. "
                        "Se houver 2+ contratos, ainda NAO pergunte qual contrato. "
                        "Interprete a resposta do cliente em relacao a pergunta que voce fez: "
                        "se ele confirmou, chame selecionar_contrato com escolha='sim' AGORA; "
                        "se ele ja indicou um contrato, passe esse contrato. "
                        "Nunca peca confirmacao em loop."
                    )
                chat_messages.append({"role": "system", "content": conteudo_confirmacao})

            # Pin de localização → forçar consulta_viabilidade com as coordenadas
            force_viabilidade_coords = False
            _loc_lat = _loc_lng = None
            _msg_loc = mensagem or ""
            _lat_m = re.search(r"latitude\s*=\s*(-?\d+(?:[.,]\d+)?)", _msg_loc, re.I)
            _lng_m = re.search(r"longitude\s*=\s*(-?\d+(?:[.,]\d+)?)", _msg_loc, re.I)
            if _lat_m and _lng_m:
                _loc_lat = _lat_m.group(1).replace(",", ".")
                _loc_lng = _lng_m.group(1).replace(",", ".")
            _has_viab_tool = any(
                (t.get("function") or {}).get("name") == "consulta_viabilidade"
                for t in (tools or [])
            )
            if _loc_lat and _loc_lng and _has_viab_tool:
                force_viabilidade_coords = True
                chat_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "OBRIGATORIO: o cliente enviou a localizacao atual com coordenadas. "
                            f"Chame consulta_viabilidade AGORA com latitude={_loc_lat} e longitude={_loc_lng}. "
                            "Nao peca endereco antes. Nao responda so em texto sem chamar a tool."
                        ),
                    }
                )

            results_history = []
            final_response_text = ""
            audit = ToolCallLog()
            import time as _time
            wall_started = _time.perf_counter()

            pergunta_contrato_pendente = (
                self._agent_mode(provedor) != "support"
                and bool(conversation_state.get("confirmacao_pedida"))
                and not conversation_state.get("contrato_escolhido")
                and bool(
                    conversation_state.get("precisa_confirmar_dados")
                    or conversation_state.get("precisa_escolher_contrato")
                )
                and "selecionar_contrato" in tool_names
            )
            repeticoes_pergunta_contrato = 0
            force_selecionar_contrato = False
            espera_checada = False

            for _turn in range(5):
                kwargs = {
                    "model": model,
                    "messages": chat_messages,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                    if force_viabilidade_coords and _turn == 0:
                        kwargs["tool_choice"] = {
                            "type": "function",
                            "function": {"name": "consulta_viabilidade"},
                        }
                        force_viabilidade_coords = False
                    elif force_selecionar_contrato:
                        kwargs["tool_choice"] = {
                            "type": "function",
                            "function": {"name": "selecionar_contrato"},
                        }
                        force_selecionar_contrato = False
                    else:
                        kwargs["tool_choice"] = "auto"

                response = None
                for attempt in range(3):
                    try:
                        response = await asyncio.to_thread(client.chat.completions.create, **kwargs)
                        break
                    except Exception as api_err:
                        err_txt = str(api_err).lower()
                        transient = (
                            "disconnected" in err_txt
                            or "timeout" in err_txt
                            # Instabilidade nos servidores do provedor de IA (5xx):
                            # o SDK já fez os retries internos; damos mais uma chance
                            # com espera maior antes de deixar o cliente sem resposta.
                            or "server_error" in err_txt
                            or "service unavailable" in err_txt
                            or "error code: 500" in err_txt
                            or "error code: 502" in err_txt
                            or "error code: 503" in err_txt
                        )
                        if attempt < 2 and transient:
                            await asyncio.sleep(2 * (attempt + 1))
                            continue
                        raise

                if not response or not response.choices:
                    raise Exception("Falha na API de IA")

                choice = response.choices[0]
                msg = choice.message
                tool_calls = msg.tool_calls or []
                usage = getattr(response, "usage", None)

                if not tool_calls:
                    final_response_text = (msg.content or "").strip()
                    log_llm_decision(
                        turn=_turn + 1,
                        tool_calls=None,
                        text_reply=final_response_text,
                    )
                    if (
                        pergunta_contrato_pendente
                        and _turn < 4
                        and not conversation_state.get("contrato_escolhido")
                        and _repete_dados_contrato(final_response_text, conversation_state)
                    ):
                        repeticoes_pergunta_contrato += 1
                        logger.warning(
                            "[AI] Pergunta de contrato repetida | conv=%s | tentativa=%s",
                            conversation_id, repeticoes_pergunta_contrato,
                        )
                        if repeticoes_pergunta_contrato == 1:
                            chat_messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "Voce esta repetindo os dados do contrato que JA mostrou, e o cliente JA respondeu "
                                        "a sua pergunta com a mensagem atual. NAO repita a pergunta. "
                                        "Decida pela resposta dele: se confirmou ou indicou um contrato, chame "
                                        "selecionar_contrato agora; se negou, peca o dado correto; "
                                        "se falou de outro assunto, responda a esse assunto."
                                    ),
                                }
                            )
                            continue
                        if repeticoes_pergunta_contrato == 2:
                            chat_messages.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "Chame selecionar_contrato agora. Em escolha, coloque o que o cliente respondeu "
                                        "a sua pergunta, como voce entendeu: 'sim' se ele confirmou, o numero/id do "
                                        "contrato se ele indicou um, ou 'nao' se ele negou."
                                    ),
                                }
                            )
                            force_selecionar_contrato = True
                            continue
                    if (
                        tools
                        and not espera_checada
                        and _turn < 4
                        and await self._deixa_cliente_esperando(
                            client, model, mensagem, final_response_text,
                            [h["name"] for h in results_history],
                        )
                    ):
                        espera_checada = True
                        logger.warning(
                            "[AI] Resposta deixaria o cliente esperando sem acao | conv=%s | resposta=%s",
                            conversation_id, final_response_text[:120],
                        )
                        chat_messages.append({"role": "assistant", "content": final_response_text})
                        chat_messages.append({"role": "system", "content": ESPERA_CORRECAO_MSG})
                        final_response_text = ""
                        continue
                    break

                log_llm_decision(turn=_turn + 1, tool_calls=tool_calls)

                chat_messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments or "{}",
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )

                early_return = None
                pending_system_after_tools: list = []
                for tc in tool_calls:
                    fname = tc.function.name
                    try:
                        fargs = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        fargs = {}

                    logger.info("[AI] Executando tool %s args=%s", fname, fargs)
                    res = await self.executor.execute(
                        provedor,
                        fname,
                        fargs,
                        contexto,
                        conversation_id,
                        mensagem=mensagem,
                        messages=messages,
                        audit=audit,
                    )
                    resolved = self.executor.registry.resolve_name(fname)
                    results_history.append({"name": resolved, "response": res})

                    # Atualiza estado local; system messages só DEPOIS de todas as
                    # respostas tool (OpenAI exige tool msgs logo após tool_calls).
                    if resolved == "selecionar_contrato" and isinstance(res, dict):
                        if res.get("contrato_escolhido"):
                            conversation_state["contrato_escolhido"] = True
                            conversation_state["precisa_confirmar_dados"] = False
                            conversation_state["precisa_escolher_contrato"] = False
                            conversation_state["dados_confirmados"] = True
                            if res.get("contrato_id"):
                                conversation_state["contrato_id"] = res.get("contrato_id")
                            pending_system_after_tools.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "Confirmacao registrada no Redis (contrato_escolhido=true). "
                                        "NUNCA peca o cliente confirmar os dados do cadastro de novo. "
                                        "Continue com o pedido original."
                                    ),
                                }
                            )
                        elif res.get("precisa_escolher_contrato") and res.get("dados_confirmados"):
                            conversation_state["dados_confirmados"] = True
                            conversation_state["precisa_confirmar_dados"] = False
                            conversation_state["precisa_escolher_contrato"] = True
                            conversation_state["contrato_escolhido"] = False
                            pending_system_after_tools.append(
                                {
                                    "role": "system",
                                    "content": (
                                        "Dados do cadastro confirmados no Redis. "
                                        "NAO peca confirmar nome/endereco de novo. "
                                        "Pergunte com naturalidade para qual contrato e este atendimento "
                                        "e aguarde a escolha (depois chame selecionar_contrato)."
                                    ),
                                }
                            )

                    chat_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                self.executor.filter_result_for_prompt(res, fname),
                                ensure_ascii=False,
                                default=str,
                            ),
                        }
                    )

                for sys_msg in pending_system_after_tools:
                    chat_messages.append(sys_msg)

                # A IA redige a resposta no próximo turno com base no retorno das tools

            final_response_text = self.formatter.corrigir_formato_resposta(
                final_response_text,
                conversation_id=conversation_id,
                provedor_id=provedor.id,
                channel=channel,
                phone=contact_phone,
            )
            final_response_text = self.formatter.aplicar_regra_emojis(final_response_text, provedor)
            estado_final_updates = {
                "last_ia_response": final_response_text,
                "last_ia_action": results_history[-1]["name"] if results_history else None,
                "tool_audit": audit.summary(),
            }
            if self._agent_mode(provedor) != "support" and final_response_text:
                try:
                    mem_final = await redis_memory_service.get_ai_memory(
                        provedor.id, conversation_id, channel, contact_phone
                    )
                    estado_final = mem_final.get("state") or {}
                    aguardando = not estado_final.get("contrato_escolhido") and bool(
                        estado_final.get("precisa_confirmar_dados")
                        or estado_final.get("precisa_escolher_contrato")
                    )
                    if aguardando:
                        estado_final_updates["confirmacao_pedida"] = True
                except Exception:
                    logger.debug("[AI] Falha ao marcar confirmacao_pedida", exc_info=True)
            await redis_memory_service.update_ai_state(
                provedor.id,
                conversation_id,
                estado_final_updates,
                channel,
                contact_phone,
            )
            latency_ms = round((_time.perf_counter() - wall_started) * 1000, 1)
            log_usage(
                provedor_id=provedor.id,
                conversation_id=conversation_id,
                model=model,
                provider=provider_name,
                latency_ms=latency_ms,
                tool_summary=audit.summary(),
            )
            log_turn_end(
                conversation_id=conversation_id,
                resposta=final_response_text or "",
                tool_summary=audit.summary(),
                latency_ms=latency_ms,
                early_return=False,
            )
            return {
                "success": True,
                "resposta": final_response_text or "Desculpe, tente novamente.",
                "ai_conversation_id": ai_conversation_id,
                "tool_audit": audit.summary(),
            }

        except Exception as e:
            logger.error("[AI] Erro: %s", e, exc_info=True)
            return {"success": False, "erro": str(e)}
        finally:
            try:
                await redis_memory_service.update_ai_state(
                    provedor.id, conversation_id, {"locked": False}, channel, contact_phone
                )
            except Exception:
                pass
            await redis_memory_service.release_lock(
                provedor.id, conversation_id, channel, contact_phone
            )

    def generate_response_sync(
        self, mensagem: str, provedor: Provedor, contexto: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        return async_to_sync(self.generate_response)(mensagem, provedor, contexto)

    async def correct_text(self, text: str, language: str = "pt-BR", provedor: Provedor = None) -> str:
        try:
            if not provedor:
                return text
            client = self._client_for(provedor)
            if not client:
                return text
            model = get_provedor_openai_model(provedor)
            prompt = (
                f"Corrija o texto abaixo para {language} correto, natural e profissional. "
                f"Não altere o significado. Texto: {text}"
            )
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1000,
            )
            corrected = (response.choices[0].message.content or "").strip()
            if (corrected.startswith('"') and corrected.endswith('"')) or (
                corrected.startswith("'") and corrected.endswith("'")
            ):
                corrected = corrected[1:-1]
            return corrected or text
        except Exception as e:
            logger.error("[AI] Erro ao corrigir texto: %s", e)
            return text

    def process_pdf_with_ai(
        self, pdf_path: str, provedor: Provedor, contexto: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            client = self._client_for(provedor)
            if not client:
                return {"success": False, "erro": OPENAI_KEY_MISSING_MSG}
            text_parts = []
            try:
                import pdfplumber

                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages[:10]:
                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            text_parts.append(page_text.strip())
            except Exception as e:
                logger.warning("[AI] pdfplumber falhou: %s", e)

            pdf_text = "\n\n".join(text_parts).strip()
            if not pdf_text:
                return {
                    "success": True,
                    "resposta": "Recebi o PDF, mas não consegui extrair texto legível do arquivo.",
                    "pdf_info": {"pages_text": 0},
                }

            model = get_provedor_openai_model(provedor)
            contact_name = (contexto or {}).get("contact_name") or "cliente"
            file_name = (contexto or {}).get("file_name") or "documento.pdf"
            prompt = (
                f"O cliente {contact_name} enviou o PDF \"{file_name}\". "
                f"Resuma o conteúdo de forma clara e objetiva em português.\n\n"
                f"Conteúdo:\n{pdf_text[:12000]}"
            )
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=800,
            )
            answer = (response.choices[0].message.content or "").strip()
            return {
                "success": True,
                "resposta": answer or "Recebi o PDF.",
                "pdf_info": {"chars": len(pdf_text)},
            }
        except Exception as e:
            logger.error("[AI] Erro ao processar PDF: %s", e, exc_info=True)
            return {"success": False, "erro": str(e)}

    def analyze_image_with_ai(
        self, image_path: str, provedor: Provedor, contexto: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        try:
            client = self._client_for(provedor)
            if not client:
                return {"success": False, "erro": OPENAI_KEY_MISSING_MSG}

            with open(image_path, "rb") as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode("ascii")
            mime = "image/jpeg"
            if raw.startswith(b"\x89PNG"):
                mime = "image/png"
            elif raw.startswith(b"GIF8"):
                mime = "image/gif"
            elif raw.startswith(b"RIFF"):
                mime = "image/webp"

            model = get_provedor_ai_model(provedor)
            provider = get_provedor_ai_provider(provedor)
            if provider == "gemini":
                vision_model = model if "gemini" in model else "gemini-2.0-flash"
            elif provider == "deepseek":
                vision_model = model
            else:
                vision_model = (
                    model
                    if "gpt-4o" in model or "gpt-4.1" in model or "o1" in model
                    else "gpt-4o-mini"
                )
            from ai.media_inbound import CATEGORIAS_DEFINICAO, split_categoria

            prompt = (
                "Analise a imagem enviada pelo cliente de um provedor de internet. "
                "Descreva de forma objetiva, em português, o que a imagem mostra e os textos/"
                "números relevantes que estiverem legíveis.\n"
                "Se for pagamento ou cobrança, cite valor, data/hora, instituição e "
                "destinatário/origem quando visíveis. "
                "Se for modem/roteador, identifique os LEDs visíveis (Power, LOS/PON/fibra, LAN, Wi-Fi) "
                "e a cor de cada um. Se houver LED vermelho, diga qual parece ser "
                "(muitas vezes é o LOS/fibra). Não conclua sozinho que precisa de técnico.\n"
                "Na descrição, não diga se a imagem é ou não é comprovante.\n\n"
                "Na ÚLTIMA linha escreva exatamente \"CATEGORIA: <categoria>\", com uma destas:\n"
                f"{CATEGORIAS_DEFINICAO}"
            )
            response = client.chat.completions.create(
                model=vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"},
                            },
                        ],
                    }
                ],
                temperature=0.3,
                max_tokens=500,
            )
            answer, categoria = split_categoria(response.choices[0].message.content or "")
            return {
                "success": True,
                "resposta": answer or "Recebi a imagem.",
                "categoria": categoria,
                "transferir_suporte": False,
            }
        except Exception as e:
            logger.error("[AI] Erro ao analisar imagem: %s", e, exc_info=True)
            return {"success": False, "erro": str(e)}


# Instância singleton (alias openai_service para compatibilidade de imports)
ai_service = AIService()
openai_service = ai_service
OpenAIService = AIService
