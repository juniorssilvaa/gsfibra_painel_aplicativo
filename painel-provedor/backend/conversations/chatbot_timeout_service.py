import threading
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from django.utils import timezone
from django.db import close_old_connections, transaction

logger = logging.getLogger(__name__)


def _last_customer_message_created_at(conv) -> Optional[datetime]:
    """Último created_at real de mensagem do cliente — fonte mais fiel para inatividade (evita campo desfasado vs produção)."""
    from conversations.models import Message

    dt = (
        Message.objects.filter(conversation_id=conv.id, is_from_customer=True)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return dt


def _safe_inactivity_minutes(raw) -> Optional[int]:
    """Aceita string/number do builder (globalInactivityTime)."""
    if raw is None or raw == "":
        return None
    try:
        m = int(float(str(raw).strip().replace(",", ".")))
        return m if m > 0 else None
    except (TypeError, ValueError):
        return None


DEFAULT_INACTIVITY_CLOSE_MESSAGE = (
    "Seu atendimento foi encerrado por inatividade. "
    "Caso precise de algo, basta enviar uma nova mensagem!"
)


def _format_inactivity_close_message(template: Optional[str]) -> str:
    """Mensagem ao cliente ao encerrar por inatividade global (bloco Início)."""
    t = (template or "").strip()
    return t if t else DEFAULT_INACTIVITY_CLOSE_MESSAGE


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


def run_chatbot_inactivity_scan() -> None:
    """
    Uma única passagem sobre conversas sob automação elegíveis.
    Chamado pela thread TIMEOUT_MONITOR e pelo asgi_periodic (Daphne) para redundância
    entre ambientes (evita falha silenciosa quando só um processo deveria correr threads).
    """
    from conversations.models import Conversation, Team
    from core.models import ChatbotFlow
    from core.redis_memory_service import redis_memory_service
    from core.chatbot_engine import ChatbotEngine
    from conversations.closing_service import closing_service, stamp_automation_closure_trace

    close_old_connections()

    conversations = Conversation.objects.filter(
        waiting_for_agent=False,
        status__in=["snoozed", "pending"],
    ).select_related("inbox", "inbox__provedor", "contact")

    for conv in conversations:
        try:
            provedor_id = conv.inbox.provedor_id

            # Canal só de disparo ou sem IA: não herda timeout do fluxo global
            canal = None
            try:
                canal = conv.inbox.get_canal_instance() if conv.inbox else None
            except Exception:
                canal = None
            if canal and (
                getattr(canal, "somente_disparo", False)
                or getattr(canal, "ia_ativa", True) is False
            ):
                continue

            state = redis_memory_service.get_ai_state_sync(
                provedor_id,
                conv.id,
                conv.inbox.channel_type,
                conv.contact.phone,
            )

            node_id = state.get("chatbot_node_id")

            canal_pk = _canal_pk_from_inbox_for_flow(conv)
            flow = None
            if canal_pk:
                flow = ChatbotFlow.objects.filter(
                    provedor_id=provedor_id,
                    canal_id=canal_pk,
                ).order_by("-updated_at").first()
            # Sem fluxo vinculado a ESTE canal: não usar fallback global (quebrava canais de disparo)
            if not flow:
                continue

            start_node = next((n for n in (flow.nodes or []) if n.get("type") == "start"), None)
            if not start_node:
                continue

            start_data = start_node.get("data", {}) or {}
            inactivity_minutes = _safe_inactivity_minutes(start_data.get("globalInactivityTime"))
            timeout_action = start_data.get("globalTimeoutAction", "nothing")

            if not inactivity_minutes or timeout_action == "nothing":
                continue

            last_msg_time = (
                _last_customer_message_created_at(conv)
                or conv.last_user_message_at
                or conv.last_message_at
                or conv.updated_at
            )
            if not last_msg_time:
                continue

            threshold = last_msg_time + timedelta(minutes=inactivity_minutes)

            if timezone.now() > threshold:
                logger.info(
                    f"⏳ [TIMEOUT] Conv {conv.id} inativa há >{inactivity_minutes}min. "
                    f"Ação: {timeout_action}"
                )

                conv_id = conv.id

                if timeout_action == "transfer":
                    transfer_msg = None
                    transfer_team_name = None
                    with transaction.atomic():
                        # Lock sem select_related — PostgreSQL rejeita FOR UPDATE em outer join.
                        conv_locked = Conversation.objects.select_for_update().get(id=conv_id)
                        if conv_locked.waiting_for_agent:
                            continue
                        if not isinstance(conv_locked.additional_attributes, dict):
                            conv_locked.additional_attributes = {}
                        if conv_locked.additional_attributes.get("chatbot_timeout_transfer_handled") is True:
                            continue
                        conv_locked.additional_attributes["chatbot_timeout_transfer_handled"] = True

                        flow_context = state.get("flow_context", {}) if isinstance(state, dict) else {}

                        preferred_team_id = None
                        if node_id:
                            current_node = next(
                                (n for n in (flow.nodes or []) if n.get("id") == node_id),
                                None,
                            )
                            if current_node:
                                c_data = current_node.get("data", {})
                                if c_data.get("maxInvalidAction") == "transfer_direct":
                                    preferred_team_id = c_data.get("maxInvalidActionTeamId")

                        if not preferred_team_id:
                            preferred_team_id = flow_context.get("last_routing_team_id")

                        if not preferred_team_id:
                            preferred_team_id = start_data.get("globalTimeoutTeamId")

                        team = None
                        if preferred_team_id:
                            try:
                                team = Team.objects.filter(
                                    id=int(preferred_team_id),
                                    provedor_id=provedor_id,
                                    is_active=True,
                                ).first()
                            except (TypeError, ValueError):
                                team = None

                        conv_locked.status = "pending"
                        conv_locked.team = team
                        conv_locked.assignee = None
                        conv_locked.waiting_for_agent = True
                        conv_locked.save(
                            update_fields=[
                                "status",
                                "team",
                                "assignee",
                                "waiting_for_agent",
                                "additional_attributes",
                            ]
                        )
                        custom_tpl = start_data.get("globalTimeoutTransferMessage")
                        transfer_msg = _format_inactivity_transfer_message(custom_tpl, team)
                        transfer_team_name = team.name if team else None

                    if not transfer_msg:
                        continue

                    conv = Conversation.objects.select_related(
                        "inbox", "inbox__provedor", "contact"
                    ).get(id=conv_id)
                    try:
                        ok, detail = ChatbotEngine.send_message_agnostic_sync(conv=conv, text=transfer_msg)
                        if not ok:
                            logger.warning(
                                f"Falha ao enviar aviso de transferência (conv {conv.id}): {detail}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Falha ao enviar aviso de transferência (conv {conv.id}): {e}",
                            exc_info=True,
                        )

                    redis_memory_service.clear_memory_sync(
                        provedor_id, conv.id, conv.inbox.channel_type, conv.contact.phone
                    )
                    if transfer_team_name:
                        logger.info(
                            f"✅ [TIMEOUT] Conv {conv.id} transferida para equipe {transfer_team_name} (origem do fluxo)."
                        )
                    else:
                        logger.info(
                            f"✅ [TIMEOUT] Conv {conv.id} transferida para fila humana (sem equipe inferida)."
                        )

                elif timeout_action == "close":
                    close_msg = None
                    with transaction.atomic():
                        # Lock sem select_related — PostgreSQL rejeita FOR UPDATE em outer join.
                        conv_locked = Conversation.objects.select_for_update().get(id=conv_id)
                        if conv_locked.waiting_for_agent:
                            continue
                        if not isinstance(conv_locked.additional_attributes, dict):
                            conv_locked.additional_attributes = {}
                        if conv_locked.additional_attributes.get("chatbot_timeout_close_handled") is True:
                            continue
                        conv_locked.additional_attributes["chatbot_timeout_close_handled"] = True
                        conv_locked.save(update_fields=["additional_attributes"])
                        custom_close = start_data.get("globalTimeoutCloseMessage")
                        close_msg = _format_inactivity_close_message(custom_close)

                    if not close_msg:
                        continue

                    conv = Conversation.objects.select_related(
                        "inbox", "inbox__provedor", "contact"
                    ).get(id=conv_id)
                    try:
                        ok, detail = ChatbotEngine.send_message_agnostic_sync(conv=conv, text=close_msg)
                        if not ok:
                            logger.warning(
                                f"Falha ao enviar aviso de encerramento (conv {conv.id}): {detail}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Falha ao enviar aviso de encerramento (conv {conv.id}): {e}",
                            exc_info=True,
                        )

                    stamp_automation_closure_trace(conv, "chatbot_inactivity_timeout")
                    closing_service.request_closing(conv)
                    redis_memory_service.clear_memory_sync(
                        provedor_id, conv.id, conv.inbox.channel_type, conv.contact.phone
                    )
                    logger.info(f"✅ [TIMEOUT] Conv {conv.id} encerrada automaticamente.")

        except Exception as conv_err:
            logger.error(f"❌ [TIMEOUT_MONITOR] Erro ao processar conversa {conv.id}: {conv_err}")


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
                run_chatbot_inactivity_scan()
            except Exception as loop_err:
                logger.error(f"❌ [TIMEOUT_MONITOR] Erro no loop de monitoramento: {loop_err}")
            
            # Aguardar 60 segundos antes da próxima varredura
            time.sleep(60)

# Instância global
chatbot_timeout_service = ChatbotTimeoutService()
