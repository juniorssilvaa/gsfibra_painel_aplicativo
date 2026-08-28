import re
import logging
import json
import time
from typing import Any, Dict, Optional

from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


def _debug_log(message: str, data: Dict[str, Any], *, location: str, hypothesis_id: str, run_id: str = "run1") -> None:
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        log_path = r"e:\niochat\.cursor\debug.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


YES_WORDS = {
    "sim", "s", "ok", "certo", "correto", "confirmo", "pode", "manda", "isso", "perfeito", "pode mandar",
    "sim por favor", "está correto", "esta correto"
}

NO_WORDS = {
    "não", "nao", "n", "não preciso", "nao preciso", "só isso", "so isso", "só isso mesmo", "so isso mesmo",
    "obrigado", "obrigada", "obrigad", "valeu", "tchau", "até logo", "ate logo", "tudo certo", "já está bom",
    "ja esta bom", "está bom", "esta bom", "perfeito", "resolvido", "tá resolvido", "ta resolvido",
    "não preciso de mais nada", "nao preciso de mais nada", "não precisa", "nao precisa", "tudo ok", "ok"
}

FATURA_KEYWORDS = {
    "fatura", "boleto", "segunda via", "2 via", "2via", "vencimento", "conta", "cobrança", "cobranca", "pix", "pagar"
}

OTHER_FLOW_KEYWORDS = {
    "instala", "instalação", "instalacao", "técnico", "tecnico", "internet", "sem internet", "caiu", "lent", "wifi",
    "roteador", "modem", "chamado", "suporte"
}


def _extract_cpf_cnpj(text: str) -> Optional[str]:
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    if len(digits) in (11, 14) and digits.isdigit():
        return digits
    return None


def _detect_payment_type(text: str) -> Optional[str]:
    if not text:
        return None
    t = text.lower()
    if "pix" in t:
        return "pix"
    if "boleto" in t:
        return "boleto"
    return None


def _is_yes(text: str) -> bool:
    if not text:
        return False
    return text.strip().lower() in YES_WORDS


def _is_fatura_intent(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in FATURA_KEYWORDS)


def _is_other_flow_intent(text: str) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in OTHER_FLOW_KEYWORDS)


def _parse_contract_choice(text: str, mem: Dict[str, Any]) -> Optional[int]:
    """
    Aceita:
    - índice (1..N) quando mem['contratos'] existir
    - contrato_id direto (número >= 3 dígitos) quando bater em algum contrato da lista
    """
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text.strip())
    if not digits:
        return None

    contratos = mem.get("contratos") or []
    try:
        choice_num = int(digits)
    except Exception:
        return None

    if contratos and 1 <= choice_num <= len(contratos):
        try:
            return int(contratos[choice_num - 1].get("contratoId") or contratos[choice_num - 1].get("contrato_id"))
        except Exception:
            return None

    # Se digitou um contrato_id direto
    if contratos and choice_num >= 100:
        for c in contratos:
            try:
                cid = int(c.get("contratoId") or c.get("contrato_id"))
            except Exception:
                continue
            if cid == choice_num:
                return cid

    return None


async def try_handle_fatura_flow(*, mensagem: str, provedor, contexto: Dict[str, Any], redis_memory_service, actions_handler) -> Optional[Dict[str, Any]]:
    """
    Fluxo determinístico de FATURA.
    Retorna dict {success, resposta, final_action?, ai_conversation_id?} se tratado.
    Retorna None se não for fluxo FATURA (deixa o orquestrador seguir para IA genérica).
    """
    conversation = (contexto or {}).get("conversation")
    if not conversation:
        return None

    provedor_id = provedor.id
    conversation_id = conversation.id
    
    channel = redis_memory_service.normalize_channel((contexto or {}).get("canal", "whatsapp"))
    contact = (contexto or {}).get("contact")
    phone = contact.phone if contact else (contexto or {}).get("contact_phone", "unknown")

    logger.info(f"[FATURA_FLOW] TRACE | conv={conversation_id} | msg='{mensagem}' | channel={channel}")

    # region agent log
    _debug_log(
        "fatura_flow_entry",
        {
            "provedor_id": provedor_id,
            "conversation_id": conversation_id,
            "channel": channel,
            "phone": phone,
            "msg_len": len(mensagem or ""),
            "msg_has_cpf": bool(_extract_cpf_cnpj(mensagem)),
        },
        location="deterministic_fatura_flow.py:try_handle_fatura_flow:entry",
        hypothesis_id="H5",
    )
    # endregion

    mem = await redis_memory_service.get_ai_state(provedor_id, conversation_id, channel, phone)
    flow = mem.get("flow") or "NONE"
    step = mem.get("step") or "INICIAL"

    start_fatura = _is_fatura_intent(mensagem)
    in_fatura = (flow == "FATURA")
    in_suspensao = (flow == "SUSPENSO")

    # region agent log
    _debug_log(
        "fatura_flow_state",
        {
            "provedor_id": provedor_id,
            "conversation_id": conversation_id,
            "flow": flow,
            "step": step,
            "start_fatura": start_fatura,
            "in_fatura": in_fatura,
            "in_suspensao": in_suspensao,
        },
        location="deterministic_fatura_flow.py:try_handle_fatura_flow:state",
        hypothesis_id="H5",
    )
    # endregion

    # Se estiver em fluxo de suspensão, o determinístico não deve interceptar (deixar Gemini tratar opções 1 e 2)
    if in_suspensao:
        return None

    # 🚨 VERIFICAÇÃO CRÍTICA: Se não está em fluxo de fatura e a mensagem atual não é intenção de fatura,
    # verificar se o contexto original era sobre problema de internet
    # Se sim, NÃO iniciar fluxo de fatura mesmo que tenha palavras-chave ambíguas
    if not in_fatura and not start_fatura:
        # Verificar histórico para ver se o contexto original era sobre internet
        history_items = await redis_memory_service.get_ai_context(provedor_id, conversation_id, channel, phone, limit=15)
        internet_problem_keywords = ["internet", "sem internet", "internet lenta", "internet caiu", "internet caindo", 
                                     "sem sinal", "sem acesso", "problema", "problema na internet", "internet não funciona",
                                     "wifi", "roteador", "modem", "led vermelho", "sinal", "conexão", "conexao"]
        
        # Verificar nas primeiras mensagens do cliente se mencionou problema de internet
        for msg_data in history_items:
            if msg_data.get('role') == 'user':
                content_lower = (msg_data.get('content') or '').lower()
                # Verificar se é uma das primeiras mensagens do cliente (não apenas CPF/CNPJ)
                if len(content_lower) > 20:  # Mensagens maiores que apenas CPF/CNPJ
                    if any(keyword in content_lower for keyword in internet_problem_keywords):
                        # Contexto original é sobre internet - NÃO iniciar fluxo de fatura
                        logger.info(f"[FATURA_FLOW] Contexto original é internet - não iniciando fluxo de fatura na conversa {conversation_id}")
                        return None
        
        return None

    # Anti-mistura de fluxo: se já estamos em FATURA, não deixar desviar.
    if in_fatura and _is_other_flow_intent(mensagem) and step not in ("FATURA_ENVIADA",):
        await redis_memory_service.update_ai_state(
            provedor_id,
            conversation_id,
            {"flow": "FATURA", "step": step},
            channel,
            phone
        )
        # Estado atualizado - deixar IA gerar mensagem personalizada
        return None

    # Inicialização do fluxo
    if not in_fatura:
        flow = "FATURA"
        step = "AGUARDANDO_CPF_CNPJ"
        await redis_memory_service.update_ai_state(
            provedor_id,
            conversation_id,
            {"flow": flow, "step": step, "fatura_enviada": False, "last_function": None},
            channel,
            phone
        )

    # Se já foi enviada, verificar se cliente está satisfeito
    if mem.get("fatura_enviada") and step == "FATURA_ENVIADA":
        # Detectar se o cliente está satisfeito e quer encerrar
        mensagem_lower = mensagem.lower().strip()
        cliente_satisfeito = any(
            palavra in mensagem_lower 
            for palavra in NO_WORDS
        )
        
        if cliente_satisfeito:
            # Cliente está satisfeito - apenas confirmar e deixar IA decidir
            logger.info(f"[FATURA_FLOW] Cliente satisfeito detectado na conversa {conversation_id}")
            return {
                "success": True,
                "resposta": "Perfeito! Fico feliz em ter ajudado. Se precisar de mais alguma coisa, estou à disposição! 👋",
                "final_action": "CLIENTE_SATISFEITO",
                "ai_conversation_id": f"ai:{provedor_id}:{conversation_id}",
            }
        
        # Cliente ainda pode precisar de ajuda - perguntar novamente
        return {
            "success": True,
            "resposta": "Sua fatura já foi enviada aqui no WhatsApp. Precisa de mais alguma coisa?",
            "final_action": "FATURA_JA_ENVIADA",
            "ai_conversation_id": f"ai:{provedor_id}:{conversation_id}",
        }

    # Etapa 1: solicitar CPF/CNPJ
    if step == "AGUARDANDO_CPF_CNPJ":
        cpf = _extract_cpf_cnpj(mensagem)
        if not cpf:
            await redis_memory_service.update_ai_state(
                provedor_id,
                conversation_id,
                {"flow": "FATURA", "step": "AGUARDANDO_CPF_CNPJ"},
                channel,
                phone
            )
            # Não retornar resposta fixa - deixar a IA gerar mensagem personalizada
            # Retornar None para que a IA decida como pedir o CPF/CNPJ baseado no contexto
            return None

        await redis_memory_service.update_ai_state(
            provedor_id,
            conversation_id,
            {"flow": "FATURA", "step": "CLIENTE_VALIDADO", "cpf_cnpj": cpf},
            channel,
            phone
        )

        # Consulta determinística (sem deixar o modelo decidir)
        # region agent log
        _debug_log(
            "fatura_flow_call_execute",
            {
                "provedor_id": provedor_id,
                "conversation_id": conversation_id,
                "cpf_len": len(cpf) if cpf else None,
                "step": step,
            },
            location="deterministic_fatura_flow.py:try_handle_fatura_flow:call",
            hypothesis_id="H6",
        )
        # endregion
        res = await sync_to_async(actions_handler.execute_sgp_function)(
            provedor,
            "consultar_cliente_sgp",
            {"cpf_cnpj": cpf, "provedor_id": provedor_id, "conversation_id": conversation_id},
            contexto,
        )
        if not res.get("success"):
            await redis_memory_service.update_ai_state(
                provedor_id,
                conversation_id,
                {"flow": "FATURA", "step": "AGUARDANDO_CPF_CNPJ"},
                channel,
                phone
            )
            # Estado atualizado - deixar IA gerar mensagem personalizada
            return None

        # A função já retorna mensagem formatada (contratos/seleção)
        msg = res.get("mensagem_formatada") or "Encontrei seu cadastro. Me confirme os dados do contrato para continuar."
        return {
            "success": True,
            "resposta": msg,
            "final_action": "consultar_cliente_sgp",
            "ai_conversation_id": f"ai:{provedor_id}:{channel}:{conversation_id}",
        }

    # Etapa de escolha de contrato (quando houver múltiplos)
    if step == "AGUARDANDO_ESCOLHA_CONTRATO":
        contrato_id = _parse_contract_choice(mensagem, mem)
        if not contrato_id:
            return {
                "success": True,
                "resposta": "Perfeito. Qual contrato você deseja? Responda com o número da opção (ex: 1) ou com o número do contrato.",
                "final_action": "ASK_CONTRATO",
                "ai_conversation_id": f"ai:{provedor_id}:{channel}:{conversation_id}",
            }

        await redis_memory_service.update_ai_state(
            provedor_id,
            conversation_id,
            {"flow": "FATURA", "step": "AGUARDANDO_CONFIRMACAO_CONTRATO", "contrato_id": contrato_id},
            channel,
            phone
        )
        return {
            "success": True,
            "resposta": f"Perfeito. Confirme por favor: é para o contrato {contrato_id}? (sim/não)",
            "final_action": "CONFIRM_CONTRATO",
            "ai_conversation_id": f"ai:{provedor_id}:{channel}:{conversation_id}",
        }

    # Etapa de confirmação e geração/envio
    if step in ("CLIENTE_VALIDADO", "AGUARDANDO_CONFIRMACAO_CONTRATO"):
        if not _is_yes(mensagem) and step != "CLIENTE_VALIDADO":
            return {
                "success": True,
                "resposta": "Tudo bem. Me diga qual contrato é o correto (número do contrato ou a opção da lista).",
                "final_action": "WAIT_CONFIRM_OR_CHOICE",
                "ai_conversation_id": f"ai:{provedor_id}:{channel}:{conversation_id}",
            }

        # 🚨 VERIFICAÇÃO CRÍTICA: Verificar se o contexto original era sobre problema de internet
        # Se o cliente entrou reclamando de internet, NÃO enviar fatura quando confirmar dados
        # Deixar a IA genérica continuar com o suporte de internet
        history_items = await redis_memory_service.get_ai_context(provedor_id, conversation_id, channel, phone, limit=15)
        
        # Verificar nas primeiras mensagens do cliente se mencionou problema de internet
        internet_problem_keywords = ["internet", "sem internet", "internet lenta", "internet caiu", "internet caindo", 
                                     "sem sinal", "sem acesso", "problema", "problema na internet", "internet não funciona",
                                     "wifi", "roteador", "modem", "led vermelho", "sinal", "conexão", "conexao"]
        
        original_intent_is_internet = False
        for msg_data in history_items:
            if msg_data.get('role') == 'user':
                content_lower = (msg_data.get('content') or '').lower()
                # Verificar se é uma das primeiras mensagens do cliente (não apenas CPF/CNPJ)
                if len(content_lower) > 20:  # Mensagens maiores que apenas CPF/CNPJ
                    if any(keyword in content_lower for keyword in internet_problem_keywords):
                        original_intent_is_internet = True
                        logger.info(f"[FATURA_FLOW] Contexto original detectado: problema de internet na conversa {conversation_id}")
                        break
        
        # Se o contexto original era sobre internet e o cliente confirmou dados, NÃO enviar fatura
        # Deixar a IA genérica continuar com o suporte
        if original_intent_is_internet and _is_yes(mensagem):
            logger.info(f"[FATURA_FLOW] Cliente confirmou dados mas contexto original é internet - deixando IA genérica continuar suporte na conversa {conversation_id}")
            # Limpar o fluxo de fatura e deixar a IA genérica continuar
            await redis_memory_service.update_ai_state(
                provedor_id,
                conversation_id,
                {"flow": "NONE", "step": "INICIAL", "dados_confirmados": True},
                channel,
                phone
            )
            return None  # Deixar IA genérica continuar

        cpf = mem.get("cpf_cnpj")
        if not cpf:
            await redis_memory_service.update_ai_state(
                provedor_id,
                conversation_id,
                {"flow": "FATURA", "step": "AGUARDANDO_CPF_CNPJ"},
                channel,
                phone
            )
            # Estado atualizado - deixar IA gerar mensagem personalizada
            return None

        if mem.get("fatura_enviada") or mem.get("last_function") == "gerar_fatura_completa":
            await redis_memory_service.update_ai_state(
                provedor_id,
                conversation_id,
                {"flow": "FATURA", "step": "FATURA_ENVIADA", "fatura_enviada": True, "last_function": "gerar_fatura_completa"},
                channel,
                phone
            )
            return {
                "success": True,
                "resposta": "Sua fatura já foi enviada aqui no WhatsApp. Precisa de mais alguma coisa?",
                "final_action": "FATURA_JA_ENVIADA",
                "ai_conversation_id": f"ai:{provedor_id}:{channel}:{conversation_id}",
            }

        tipo_pagamento = _detect_payment_type(mensagem) or "pix"
        await redis_memory_service.update_ai_state(
            provedor_id,
            conversation_id,
            {"flow": "FATURA", "step": "GERANDO_FATURA", "last_function": "gerar_fatura_completa"},
            channel,
            phone
        )

        res = await sync_to_async(actions_handler.execute_sgp_function)(
            provedor,
            "gerar_fatura_completa",
            {
                "cpf_cnpj": cpf,
                "tipo_pagamento": tipo_pagamento,
                "contrato_id": mem.get("contrato_id"),
                "provedor_id": provedor_id,
                "conversation_id": conversation_id,
            },
            contexto,
        )

        if res.get("success"):
            await redis_memory_service.update_ai_state(
                provedor_id,
                conversation_id,
                {"flow": "FATURA", "step": "FATURA_ENVIADA", "fatura_enviada": True, "last_function": "gerar_fatura_completa"},
                channel,
                phone
            )
            return {
                "success": True,
                "resposta": res.get("mensagem_formatada") or "Fatura enviada com sucesso. Posso ajudar em algo mais?",
                "final_action": "gerar_fatura_completa",
                "ai_conversation_id": f"ai:{provedor_id}:{channel}:{conversation_id}",
            }

        await redis_memory_service.update_ai_state(
            provedor_id,
            conversation_id,
            {"flow": "FATURA", "step": "ERRO_FATURA"},
            channel,
            phone
        )
        err = res.get("erro") or "Falha ao enviar fatura."
        logger.warning(f"[FATURA] Falha ao gerar/enviar fatura provedor={provedor_id} conv={conversation_id}: {err}")
        # Estado atualizado - deixar IA gerar mensagem personalizada
        return None

    # Se caiu em estado não mapeado, não deixar o modelo "inventar".
    await redis_memory_service.update_ai_state(
        provedor_id,
        conversation_id,
        {"flow": "FATURA", "step": "AGUARDANDO_CPF_CNPJ"},
        channel,
        phone
    )
    # Estado não mapeado - deixar IA gerar mensagem baseada no contexto
    return None


