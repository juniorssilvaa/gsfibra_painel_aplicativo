import threading
import time
import logging
from typing import Optional
from datetime import timedelta
from django.utils import timezone
from django.db import close_old_connections, transaction
import os

logger = logging.getLogger(__name__)


def _format_inactivity_transfer_message(template: Optional[str], team) -> str:
    """Mensagem ao cliente após timeout global. Placeholders: {nome_equipe}, {team_name}, {{nome_equipe}}, {{team_name}}."""
    t = (template or "").strip()
    team_name = getattr(team, "name", None) or ""
    if not t:
        if team:
            return (
                "Como você ficou um tempo sem responder, seu atendimento foi encaminhado automaticamente "
                f"para o setor *{team_name}*."
            )
        return (
            "Como você ficou um tempo sem responder, seu atendimento foi encaminhado automaticamente "
            "para nossa equipe humana."
        )
    out = (
        t.replace("{nome_equipe}", team_name)
        .replace("{team_name}", team_name)
        .replace("{{nome_equipe}}", team_name)
        .replace("{{team_name}}", team_name)
    )
    return out


def _canal_pk_from_inbox_for_flow(conv) -> Optional[int]:
    """ChatbotFlow.canal aponta para core.Canal.id; Inbox guarda esse id em channel_id (string)."""
    ch = getattr(getattr(conv, "inbox", None), "channel_id", None) or ""
    s = str(ch).strip()
    if s.isdigit():
        return int(s)
    return None


class ChatbotTimeoutService:
    """
    Serviço de background nativo para monitorar inatividade no chatbot.
    Roda em uma thread separada dentro do processo principal do backend.
    """
    _instance = None
    _thread = None
    _stop_event = threading.Event()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ChatbotTimeoutService, cls).__new__(cls)
        return cls._instance

    def start(self):
        """Inicia o monitoramento se ainda não estiver rodando."""
        logger.info(f"🔍 [TIMEOUT_MONITOR] Tentando iniciar serviço (Thread status: {self._thread.is_alive() if self._thread else 'None'})")
        
        # Evitar múltiplas threads
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_monitor, name="ChatbotTimeoutMonitor", daemon=True)
            self._thread.start()
            logger.info("💓 [TIMEOUT_MONITOR] Thread de monitoramento iniciada com sucesso.")
        else:
            logger.info("ℹ️ [TIMEOUT_MONITOR] Serviço já está rodando, pulando inicialização.")

    def stop(self):
        """Para o monitoramento."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
            logger.info("🛑 [TIMEOUT_MONITOR] Thread de monitoramento interrompida.")

    def _run_monitor(self):
        """Loop principal de monitoramento."""
        logger.info("💓 [TIMEOUT_MONITOR] Iniciando loop de varredura (Intervalo: 60s)...")
        
        # Delay inicial para garantir que o Django carregou tudo
        time.sleep(10)

        while not self._stop_event.is_set():
            try:
                # Importações tardias para evitar problemas de carregamento circular
                from conversations.models import Conversation, Team
                from core.models import ChatbotFlow
                from core.redis_memory_service import redis_memory_service
                from core.chatbot_engine import ChatbotEngine
                from conversations.closing_service import closing_service, stamp_automation_closure_trace
                from asgiref.sync import async_to_sync

                # Garantir que as conexões do banco estão limpas (importante para threads longas)
                close_old_connections()

                # 1. Buscar conversas ativas no bot (ocultas para atendentes)
                conversations = Conversation.objects.filter(
                    waiting_for_agent=False,
                    status__in=['snoozed', 'pending']
                ).select_related('inbox', 'inbox__provedor')

                for conv in conversations:
                    try:
                        provedor_id = conv.inbox.provedor_id
                        
                        # 2. Obter memória do chatbot (agora via DB)
                        state = redis_memory_service.get_ai_state_sync(
                            provedor_id, 
                            conv.id, 
                            conv.inbox.channel_type, 
                            conv.contact.phone
                        )
                        
                        node_id = state.get("chatbot_node_id")
                        if not node_id:
                            continue

                        # 3. Buscar fluxo ativo (mesma lógica do ChatbotEngine: Canal.id, não Inbox.id)
                        canal_pk = _canal_pk_from_inbox_for_flow(conv)
                        flow = None
                        if canal_pk:
                            flow = ChatbotFlow.objects.filter(
                                provedor_id=provedor_id,
                                canal_id=canal_pk,
                            ).order_by('-updated_at').first()
                        if not flow:
                            flow = ChatbotFlow.objects.filter(
                                provedor_id=provedor_id,
                                canal__isnull=True,
                            ).order_by('-updated_at').first()

                        if not flow:
                            continue

                        # 4. Ler timeout GLOBAL definido no nó inicial do fluxo
                        start_node = next((n for n in (flow.nodes or []) if n.get('type') == 'start'), None)
                        if not start_node:
                            continue

                        start_data = start_node.get('data', {}) or {}
                        inactivity_minutes = start_data.get('globalInactivityTime')
                        timeout_action = start_data.get('globalTimeoutAction', 'nothing')
                        
                        if not inactivity_minutes or timeout_action == 'nothing':
                            continue

                        # 5. Inatividade = tempo sem resposta do cliente.
                        # last_message_at inclui envios do bot e impede o timeout; usar última mensagem do cliente.
                        last_msg_time = (
                            conv.last_user_message_at
                            or conv.last_message_at
                            or conv.updated_at
                        )
                        if not last_msg_time:
                            continue

                        threshold = last_msg_time + timedelta(minutes=int(inactivity_minutes))
                        
                        if timezone.now() > threshold:
                            logger.info(f"⏳ [TIMEOUT] Conv {conv.id} inativa há >{inactivity_minutes}min. Ação: {timeout_action}")
                            
                            with transaction.atomic():
                                # Recarregar para garantir o estado mais recente antes de agir
                                conv.refresh_from_db()
                                if conv.waiting_for_agent: # Alguém já liberou manualmente?
                                    continue

                                if timeout_action == 'transfer':
                                    flow_context = state.get("flow_context", {}) if isinstance(state, dict) else {}
                                    preferred_team_id = flow_context.get("last_routing_team_id")
                                    team = None
                                    if preferred_team_id:
                                        try:
                                            team = Team.objects.filter(
                                                id=int(preferred_team_id),
                                                provedor_id=provedor_id,
                                                is_active=True
                                            ).first()
                                        except (TypeError, ValueError):
                                            team = None

                                    conv.status = 'pending'
                                    conv.team = team
                                    conv.assignee = None
                                    conv.waiting_for_agent = True
                                    conv.save(update_fields=['status', 'team', 'assignee', 'waiting_for_agent'])
                                    
                                    # Notificar o cliente (texto configurável no nó Início: globalTimeoutTransferMessage)
                                    try:
                                        custom_tpl = start_data.get("globalTimeoutTransferMessage")
                                        msg = _format_inactivity_transfer_message(custom_tpl, team)
                                        async_to_sync(ChatbotEngine.send_message_agnostic)(conv=conv, text=msg)
                                    except Exception as e:
                                        logger.warning(f"Falha ao enviar aviso de transferência (conv {conv.id}): {e}")
                                        
                                    # Limpar memória para o bot não interferir
                                    redis_memory_service.clear_memory_sync(provedor_id, conv.id, conv.inbox.channel_type, conv.contact.phone)
                                    if team:
                                        logger.info(f"✅ [TIMEOUT] Conv {conv.id} transferida para equipe {team.name} (origem do fluxo).")
                                    else:
                                        logger.info(f"✅ [TIMEOUT] Conv {conv.id} transferida para fila humana (sem equipe inferida).")

                                elif timeout_action == 'close':
                                    try:
                                        async_to_sync(ChatbotEngine.send_message_agnostic)(
                                            conv=conv, 
                                            text="Seu atendimento foi encerrado por inatividade. Caso precise de algo, basta enviar uma nova mensagem!"
                                        )
                                    except:
                                        pass
                                    stamp_automation_closure_trace(conv, 'chatbot_inactivity_timeout')
                                    closing_service.request_closing(conv)
                                    logger.info(f"✅ [TIMEOUT] Conv {conv.id} encerrada automaticamente.")

                    except Exception as conv_err:
                        logger.error(f"❌ [TIMEOUT_MONITOR] Erro ao processar conversa {conv.id}: {conv_err}")

            except Exception as loop_err:
                logger.error(f"❌ [TIMEOUT_MONITOR] Erro no loop de monitoramento: {loop_err}")
            
            # Aguardar 60 segundos antes da próxima varredura
            time.sleep(60)

# Instância global
chatbot_timeout_service = ChatbotTimeoutService()
