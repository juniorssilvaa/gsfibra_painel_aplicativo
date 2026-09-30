"""
Cada encerramento de atendimento vira um evento de AuditLog.
A mesma conversa pode ser reaberta e encerrada várias vezes; cada ciclo conta.
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

AUTOMATION_CLOSE_ACTIONS = ('conversation_closed_ai', 'conversation_closed_timeout')
MANUAL_CLOSE_ACTIONS = ('conversation_closed_manual', 'conversation_closed_agent')

# Marcas do encerramento anterior; precisam sair quando a conversa é reaberta.
CLOSURE_MARKERS = ('encerrado_por', 'resolucao_automacao', 'closure_source', 'finalizado_por')

# Protege contra o mesmo encerramento gravado duas vezes (duplo clique, retry de task).
DUPLICATE_WINDOW_SECONDS = 120


def closure_logged_recently(conversation_id, action: str) -> bool:
    from core.models import AuditLog

    since = timezone.now() - timedelta(seconds=DUPLICATE_WINDOW_SECONDS)
    return AuditLog.objects.filter(
        conversation_id=str(conversation_id),
        action=action,
        timestamp__gte=since,
    ).exists()


def record_automation_closure(conversation) -> None:
    """Grava o encerramento feito pela IA/chatbot (local e Supabase)."""
    from core.models import AuditLog

    action = 'conversation_closed_ai'
    if closure_logged_recently(conversation.id, action):
        return

    attrs = conversation.additional_attributes or {}
    source = str(attrs.get('closure_source') or '')
    inbox = conversation.inbox
    contact = conversation.contact
    contact_name = contact.name if contact else 'Desconhecido'
    channel_type = inbox.channel_type if inbox else 'Desconhecido'
    quem = 'pelo chatbot' if source.startswith('chatbot') else 'pela IA'

    details = f"Conversa encerrada {quem} com {contact_name} via {channel_type}"
    if source:
        details += f" | Origem: {source}"

    AuditLog.objects.create(
        user=None,
        action=action,
        ip_address='127.0.0.1',
        details=details,
        provedor=inbox.provedor if inbox else None,
        conversation_id=conversation.id,
        contact_name=contact_name,
        channel_type=channel_type,
    )

    if inbox and inbox.provedor_id:
        try:
            from core.supabase_service import supabase_service

            supabase_service.save_audit(
                provedor_id=inbox.provedor_id,
                conversation_id=conversation.id,
                action=action,
                details={'resolution_type': 'automacao', 'closure_source': source, 'details': details},
                user_id=None,
                ended_at_iso=timezone.now().isoformat(),
            )
        except Exception as e:
            logger.warning('[ClosureAudit] Falha ao enviar auditoria ao Supabase conv=%s: %s', conversation.id, e)
