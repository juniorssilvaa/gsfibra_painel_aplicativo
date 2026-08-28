"""
Serviço para integração com Google Gemini

REGRA DE OURO: A IA DEVE USAR APENAS REDIS COMO MEMÓRIA
- NÃO usar Message.objects.filter() para recuperar histórico
- NÃO usar banco de dados como memória da IA
- TODAS as mensagens devem ser recuperadas do Redis
- Use redis_memory_service.get_conversation_history_sync() ou acesso direto ao Redis
"""

import os
import logging
import asyncio
from datetime import timezone as dt_timezone
import re
import json
import hashlib
from google import genai
from typing import Dict, Any, List, Optional
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Provedor, SystemConfig
from .redis_memory_service import redis_memory_service, normalize_phone_number
from .ai_actions_handler import AIActionsHandler
from .ai_response_formatter import AIResponseFormatter
from .deterministic_fatura_flow import try_handle_fatura_flow

logger = logging.getLogger(__name__)


def _filter_ai_context_by_visible_cutoff(history_items, conversation):
    """
    Remove mensagens do contexto da IA anteriores a agent_chat_visible_from
    (evita repetir respostas de transferência/fila de um ciclo encerrado).
    """
    if not conversation or not history_items:
        return history_items
    cutoff_iso = (getattr(conversation, "additional_attributes", None) or {}).get("agent_chat_visible_from")
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
                dt = timezone.make_aware(dt, dt_timezone.utc)
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


class OpenAIService:
    """
    Motor de Orquestração da IA (Mestre).
    Gerencia o fluxo principal entre o cliente, o Gemini e os sub-agentes.
    """
    def __init__(self):
        self.api_key = None
        self.model = "gemini-3-pro-preview"
        self.client = None
        self.max_tokens = 512
        self.temperature = 0.5
        
        # Inicializar Sub-agentes (Missão: Execução e Formatação)
        self.actions = AIActionsHandler(openai_service=self)
        self.formatter = AIResponseFormatter(openai_service=self)

    # --- WRAPPERS DE COMPATIBILIDADE PARA PROMPTS ---
    def _determinar_genero_nome(self, nome: str) -> str:
        return self.formatter._determinar_genero_nome(nome)

    def _get_greeting_time(self) -> str:
        """Retorna saudação baseada no horário atual de Belém"""
        from django.utils import timezone
        now = timezone.localtime(timezone.now())
        hour = now.hour
        if 5 <= hour < 12:
            return "bom dia"
        elif 12 <= hour < 18:
            return "boa tarde"
        else:
            return "boa noite"

    def _formatar_horarios_atendimento(self, horarios: list) -> str:
        return self.actions._formatar_horarios_atendimento(horarios)
    
    def _filter_function_result_for_prompt(self, res: Dict[str, Any], fname: str) -> Dict[str, Any]:
        """
        Filtra resultados de funções para remover dados sensíveis antes de adicionar ao prompt.
        Remove estruturas internas, horario_info, dados técnicos, etc.
        """
        if not isinstance(res, dict):
            return {"success": False, "erro": "Resultado inválido"}
        
        filtered = {}
        
        # Manter apenas campos seguros
        safe_fields = [
            'success', 'mensagem_formatada', 'mensagem', 'erro', 'error', 'protocolo',
            'is_suspenso', 'contrato_suspenso', 'contrato_status_display', 'motivo_status',
            'recurso_indisponivel',  # Indica que o recurso não está disponível e deve usar mensagem_formatada
            'liberado_dias', 'data_promessa',  # Informações sobre a liberação (dias e data)
            'nome', 'cliente_encontrado'  # Nome do cliente retornado pelo SGP (apenas para referência, sempre usar mensagem_formatada)
        ]
        
        # Para consultar_cliente_sgp, SEMPRE priorizar mensagem_formatada que já contém o nome correto
        if fname == "consultar_cliente_sgp" and res.get("mensagem_formatada"):
            # Retornar mensagem_formatada + campos críticos para análise de quantidade de contratos
            return {
                "success": res.get("success", False),
                "mensagem_formatada": res.get("mensagem_formatada"),
                "cliente_encontrado": res.get("cliente_encontrado", False),
                "is_suspenso": res.get("is_suspenso", False),
                "contrato_suspenso": res.get("contrato_suspenso", False),
                "contrato_status_display": res.get("contrato_status_display"),
                "motivo_status": res.get("motivo_status"),
                "quantidade_contratos": res.get("quantidade_contratos", 0),  # 🚨 CRÍTICO: Quantidade de contratos
                "tem_apenas_um_contrato": res.get("tem_apenas_um_contrato", False)  # 🚨 CRÍTICO: Flag explícita
            }
        
        for key in safe_fields:
            if key in res:
                filtered[key] = res[key]
        
        # Para executar_transferencia_conversa, extrair apenas informações relevantes
        if fname == "executar_transferencia_conversa":
            if res.get('success') and res.get('horario_info'):
                horario_info = res.get('horario_info', {})
                # Apenas indicar se está dentro do horário, sem expor estrutura
                dentro_horario = horario_info.get('dentro_horario', True)
                filtered['dentro_horario'] = dentro_horario
                if not dentro_horario and horario_info.get('proximo_horario'):
                    filtered['proximo_horario'] = horario_info.get('proximo_horario')
                if res.get('mensagem_formatada'):
                    filtered['mensagem_formatada'] = res.get('mensagem_formatada')
            # Remover horario_info completo para não expor estrutura interna
            if 'horario_info' in filtered:
                del filtered['horario_info']
        
        # Remover qualquer campo que contenha estruturas complexas
        for key in list(filtered.keys()):
            if isinstance(filtered[key], (dict, list)):
                # Manter apenas se for uma lista simples de strings
                if isinstance(filtered[key], list) and all(isinstance(item, str) for item in filtered[key]):
                    continue
                # Caso contrário, remover
                del filtered[key]
        
        return filtered

    def _get_api_key(self) -> str:
        """Busca a chave da API Google (Gemini) do banco de dados"""
        try:
            config = SystemConfig.objects.filter(key='system_config').first()
            if not config:
                config = SystemConfig.objects.first()
            if config:
                config.refresh_from_db()
                if config.google_api_key:
                    return config.google_api_key
        except Exception:
            pass
        return os.getenv('GOOGLE_API_KEY') or os.getenv('OPENAI_API_KEY')

    async def _get_api_key_async(self) -> str:
        """Versão assíncrona para buscar a chave da API"""
        return await sync_to_async(self._get_api_key)()

    async def update_api_key_async(self):
        """Atualiza o cliente genai com a chave mais recente"""
        self.api_key = await self._get_api_key_async()
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def _build_system_prompt(self, provedor: Provedor, contexto: Dict[str, Any] = None) -> str:
        """Constrói o prompt do sistema usando os arquivos de sub-agentes de prompt"""
        from .prompt_informacional import build_informational_prompt
        from .prompt_acoes import build_actions_prompt
        
        prompt_informacional = build_informational_prompt(
            provedor=provedor,
            contexto=contexto,
            openai_service=self
        )
        
        prompt_acoes = build_actions_prompt(
            provedor=provedor,
            contexto=contexto
        )
        
        return f"{prompt_informacional}\n\n{prompt_acoes}"

    async def generate_response(
        self,
        mensagem: str,
        provedor: Provedor,
        contexto: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Método Principal (Mestre): Orquestra o recebimento da missão e delega aos sub-agentes.
        Implementa LOCK de concorrência e ISOLAMENTO total por provedor.
        """
        conversation_id = None
        contact_phone = "unknown"
        channel = "wa"
        
        if contexto and contexto.get('conversation'):
            conversation_id = contexto['conversation'].id
        
        if contexto and contexto.get('contact'):
            contact_phone = contexto['contact'].phone
        elif contexto and contexto.get('contact_phone'):
            contact_phone = contexto['contact_phone']
            
        if contexto and contexto.get('canal'):
            channel = redis_memory_service.normalize_channel(contexto['canal'])
        
        if not conversation_id:
            return {"success": False, "erro": "ID da conversa não identificado no contexto."}

        # 0. Migração de estado unknown se o telefone for identificado agora
        if contact_phone and contact_phone != "unknown":
            await redis_memory_service.migrate_unknown_phone(provedor.id, conversation_id, channel, contact_phone)

        # 1. LOCK DE CONCORRÊNCIA
        lock_acquired = await redis_memory_service.acquire_lock(provedor.id, conversation_id, channel, contact_phone)
        if not lock_acquired:
            logger.warning(f"⚠️ IA já em execução para conversa {provedor.id}:{channel}:{conversation_id}:{contact_phone}. Abortando.")
            return {"success": False, "motivo": "IA_BUSY"}

        try:
            # Marcar estado como locked
            await redis_memory_service.update_ai_state(provedor.id, conversation_id, {"locked": True}, channel, contact_phone)
            await self.update_api_key_async()
            if not self.api_key:
                return {"success": False, "erro": "Chave da API Gemini não configurada."}
            
            if not self.client:
                self.client = genai.Client(api_key=self.api_key)

            # 2. Uma única leitura: estado + histórico da conversa (provedor X, conversa X)
            # 🔒 ISOLAMENTO: provedor.id garante que a IA só acessa dados deste provedor.
            # Chave Redis: ai:memory:{provedor.id}:{channel}:{conversation_id}:{phone}
            # Cada provedor tem seu próprio namespace. Novos provedores são automaticamente isolados.
            ch_norm = redis_memory_service.normalize_channel(channel)
            ph_norm = normalize_phone_number(contact_phone)
            ai_conversation_id = f"ai:{provedor.id}:{ch_norm}:{conversation_id}:{ph_norm}"
            mem = await redis_memory_service.get_ai_memory(provedor.id, conversation_id, channel, contact_phone)
            conversation_state = mem["state"]
            history_items = (mem.get("context") or [])[-15:]
            # Usar conversa do banco para o marco de sessão (objeto do contexto pode estar desatualizado)
            conv_for_cutoff = None
            if contexto and contexto.get("conversation"):
                try:
                    from conversations.models import Conversation as ConvModel

                    conv_for_cutoff = await sync_to_async(ConvModel.objects.get)(pk=conversation_id)
                except Exception:
                    conv_for_cutoff = contexto.get("conversation")
                history_items = _filter_ai_context_by_visible_cutoff(history_items, conv_for_cutoff)

            # Identificar se já houve interação da IA
            has_ai_interaction = any(msg.get('role') == 'assistant' for msg in history_items)
            
            # Montar histórico real para o Gemini
            contents = []
            for msg_data in history_items:
                try:
                    role = 'user' if msg_data.get('role') == 'user' else 'model'
                    content = msg_data.get('content', '')
                    if content:
                        contents.append(genai.types.Content(role=role, parts=[genai.types.Part(text=content)]))
                except Exception:
                    continue

            # 2.1. Fluxo determinístico obrigatório (FATURA)
            deterministic = await try_handle_fatura_flow(
                mensagem=mensagem,
                provedor=provedor,
                contexto=contexto or {},
                redis_memory_service=redis_memory_service,
                actions_handler=self.actions,
            )
            if deterministic is not None:
                texto = (deterministic.get("resposta") or "").strip()
                
                function_call = deterministic.get("function_call")
                if function_call:
                    try:
                        fname = function_call.get("name")
                        fargs = function_call.get("arguments", {})
                        if isinstance(fargs, str): fargs = json.loads(fargs)
                        
                        if fname == "encerrar_atendimento":
                            res = await sync_to_async(self.actions.execute_database_function)(provedor, fname, fargs, contexto)
                            if res.get("success") and res.get("mensagem_formatada"):
                                texto = res.get("mensagem_formatada")
                    except Exception as e:
                        logger.error(f"[MESTRE] Erro no determinístico: {e}")
                
                await redis_memory_service.update_ai_state(
                    provedor.id, conversation_id,
                    {"last_ia_response": texto, "last_function": deterministic.get("final_action")},
                    channel, contact_phone
                )
                return {
                    "success": True,
                    "resposta": texto,
                    "final_action": deterministic.get("final_action"),
                    "ai_conversation_id": ai_conversation_id,
                }

            # 3. Contexto Forte da IA
            contexto_ia = {
                "ai_conversation_id": ai_conversation_id,
                "conversation_id": conversation_id,
                "provedor_id": provedor.id,
                "provedor_nome": provedor.nome,
                "telefone": contact_phone,
                "canal": channel,
                "fluxo_atual": conversation_state.get("flow") or "NONE",
                "step_atual": conversation_state.get("step") or "INICIAL",
                "cpf_cnpj": conversation_state.get("cpf_cnpj"),
                "contrato_id": conversation_state.get("contrato_id"),
                "is_suspenso": conversation_state.get("is_suspenso"),
                "fatura_enviada": conversation_state.get("fatura_enviada"),
                "timestamp": timezone.now().isoformat()
            }

            # 4. Construir Prompt
            base_system_prompt = self._build_system_prompt(provedor, contexto)
            instrucao_dinamica = f"\n# CONTEXTO EXPLÍCITO DE EXECUÇÃO (OBRIGATÓRIO):\n{json.dumps(contexto_ia, indent=2)}\n"
            
            if has_ai_interaction:
                instrucao_dinamica += "\n# IMPORTANTE: A conversa já iniciou. NÃO se apresente novamente, NÃO diga seu nome e NÃO use saudações iniciais (Bom dia/Boa tarde) se já as usou no histórico. Foque apenas em responder diretamente ao cliente.\n"

            system_prompt = f"""# INSTRUÇÕES DO SISTEMA
{base_system_prompt}
{instrucao_dinamica}
# CONTEXTO ATUAL: {provedor.nome} | Agente: {provedor.nome_agente_ia}

# REGRA DE RESPOSTA: Seja objetivo. Dê respostas curtas e diretas. Evite textos longos, parágrafos extensos ou repetições. Uma ou duas frases costumam ser suficientes quando possível.
"""

            # 5. Preparar Ferramentas
            tools = []
            integracoes = provedor.integracoes_externas or {}
            sgp_habilitado = integracoes.get('sgp_enabled', False) or all([integracoes.get('sgp_url'), integracoes.get('sgp_token'), integracoes.get('sgp_app')])
            
            if sgp_habilitado: tools.extend(self.actions.get_sgp_tools())
            try:
                from .database_function_definitions import DATABASE_FUNCTION_TOOLS
                tools.extend(DATABASE_FUNCTION_TOOLS)
            except: pass
            
            gemini_tools = self.actions.convert_tools_to_gemini(tools)

            # 6. Chamada ao Gemini
            final_response_text = ""
            config = {
                'temperature': self.temperature, 
                'max_output_tokens': self.max_tokens,
                'system_instruction': system_prompt
            }
            if gemini_tools: config['tools'] = [{"function_declarations": gemini_tools}]

            # Garantir que a última mensagem é a do usuário
            if not contents or contents[-1].role != 'user':
                contents.append(genai.types.Content(role='user', parts=[genai.types.Part(text=mensagem)]))
            elif contents[-1].parts[0].text != mensagem:
                contents.append(genai.types.Content(role='user', parts=[genai.types.Part(text=mensagem)]))
            
            results_history = []
            for turn in range(5):
                max_retries = 3
                response = None
                for attempt in range(max_retries):
                    try:
                        response = await asyncio.to_thread(self.client.models.generate_content, model=self.model, contents=contents, config=config)
                        break
                    except Exception as api_err:
                        if attempt < max_retries - 1 and ("RemoteProtocolError" in str(api_err) or "disconnected" in str(api_err).lower()):
                            await asyncio.sleep(1)
                            continue
                        raise api_err
                
                if not response: raise Exception("Falha Gemini")

                candidate = response.candidates[0]
                if hasattr(candidate, 'content'): contents.append(candidate.content)
                
                function_calls = []
                if hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            function_calls.append(part.function_call)
                
                if not function_calls:
                    final_response_text = response.text if hasattr(response, 'text') else ""
                    break
                
                # 7. Executar Funções (Delegação ao Actions Handler com ISOLAMENTO)
                function_responses_parts = []
                for fc in function_calls:
                    fname = fc.name
                    fargs = dict(fc.args) if hasattr(fc, 'args') else {}

                    # Forçar identidade em funções SGP/Fatura
                    if fname in ["consultar_cliente_sgp", "verificar_acesso_sgp", "gerar_fatura_completa", "criar_chamado_tecnico", "liberar_por_confianca"]:
                        fargs.update({'provedor_id': provedor.id, 'conversation_id': conversation_id})

                    logger.info(f"[MESTRE] Delegando execução de {fname} para Sub-agente de Ações")
                    
                    # Delegação total da missão ao sub-agente
                    if fname in ["consultar_cliente_sgp", "verificar_acesso_sgp", "gerar_fatura_completa", "criar_chamado_tecnico", "liberar_por_confianca"]:
                        res = await sync_to_async(self.actions.execute_sgp_function)(provedor, fname, fargs, contexto)
                    else:
                        res = await sync_to_async(self.actions.execute_database_function)(provedor, fname, fargs, contexto)

                    # Adicionar ao histórico de resultados para o prompt
                    results_history.append({"name": fname, "response": res})
                    
                    # 🚨 REGRA CRÍTICA: Se for consultar_cliente_sgp, SEMPRE retornar direto (sucesso ou erro)
                    # NUNCA deixar a IA gerar resposta para consultar_cliente_sgp - evita alucinações e nomes inventados
                    if fname == "consultar_cliente_sgp":
                        if res.get("mensagem_formatada") and res.get("cliente_encontrado"):
                            # Cliente encontrado: usar mensagem formatada do SGP
                            final_response_text = res.get("mensagem_formatada")
                        elif res.get("erro"):
                            # Cliente não encontrado: retornar erro direto, SEM deixar IA gerar
                            final_response_text = res.get("erro", "Não encontrei contratos ativos para este CPF/CNPJ.")
                        else:
                            # Fallback de segurança: erro genérico
                            final_response_text = "Não foi possível consultar os dados no momento. Tente novamente."
                        
                        await redis_memory_service.update_ai_state(
                            provedor.id, conversation_id,
                            {"last_ia_response": final_response_text, "last_ia_action": fname},
                            channel, contact_phone
                        )
                        return {
                            "success": True,
                            "resposta": final_response_text,
                            "ai_conversation_id": ai_conversation_id,
                        }
                    
                    # Se for liberar_por_confianca e retornar mensagem_formatada (sucesso ou recurso indisponível),
                    # usar a mensagem formatada diretamente como resposta final
                    if fname == "liberar_por_confianca" and res.get("mensagem_formatada"):
                        final_response_text = res.get("mensagem_formatada")
                        await redis_memory_service.update_ai_state(
                            provedor.id, conversation_id,
                            {"last_ia_response": final_response_text, "last_ia_action": fname},
                            channel, contact_phone
                        )
                        return {
                            "success": True,
                            "resposta": final_response_text,
                            "ai_conversation_id": ai_conversation_id,
                        }
                    
                    # Formatar para a resposta da função no Gemini (Usando filtro do Mestre para segurança)
                    function_responses_parts.append(genai.types.Part(
                        function_response=genai.types.FunctionResponse(
                            name=fname,
                            response=self._filter_function_result_for_prompt(res, fname)
                        )
                    ))

                # Adicionar todas as respostas de funções como um novo turno de 'user'
                if function_responses_parts:
                    contents.append(genai.types.Content(role="user", parts=function_responses_parts))

            # 9. Pós-processamento
            final_response_text = self.formatter.corrigir_formato_resposta(final_response_text, conversation_id=conversation_id, provedor_id=provedor.id, channel=channel, phone=contact_phone)
            
            updates = {'last_ia_response': final_response_text, 'last_ia_action': results_history[-1]['name'] if results_history else None}
            await redis_memory_service.update_ai_state(provedor.id, conversation_id, updates, channel, contact_phone)

            return {"success": True, "resposta": final_response_text or "Desculpe, tente novamente.", "ai_conversation_id": ai_conversation_id}

        except Exception as e:
            logger.error(f"[MESTRE] Erro: {e}", exc_info=True)
            return {"success": False, "erro": str(e)}
        finally:
            try: await redis_memory_service.update_ai_state(provedor.id, conversation_id, {"locked": False}, channel, contact_phone)
            except: pass
            await redis_memory_service.release_lock(provedor.id, conversation_id, channel, contact_phone)

    def generate_response_sync(self, mensagem: str, provedor: Provedor, contexto: Dict[str, Any] = None) -> Dict[str, Any]:
        """Versão síncrona de generate_response"""
        return async_to_sync(self.generate_response)(mensagem, provedor, contexto)

    async def correct_text(self, text: str, language: str = 'pt-BR') -> str:
        """
        Corrige gramática, ortografia e tom do texto para o idioma especificado.
        """
        try:
            await self.update_api_key_async()
            if not self.api_key:
                logger.warning("[IA] Chave de API não configurada para correção de texto.")
                return text
            
            if not self.client:
                self.client = genai.Client(api_key=self.api_key)

            prompt = f"Corrija o texto abaixo para {language} correto, natural e profissional. Não altere o significado. Texto: {text}"

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=prompt,
                config={'temperature': 0.2, 'max_output_tokens': 1000}
            )

            if response and hasattr(response, 'text') and response.text is not None:
                corrected = response.text.strip()
                if (corrected.startswith('"') and corrected.endswith('"')) or (corrected.startswith("'") and corrected.endswith("'")):
                    corrected = corrected[1:-1]
                return corrected
            return text
        except Exception as e:
            logger.error(f"[IA] Erro ao corrigir texto: {e}")
            return text

# Instância global
openai_service = OpenAIService()
