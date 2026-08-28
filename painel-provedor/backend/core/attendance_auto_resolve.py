"""
Filtro configurável: mensagens automáticas enviadas por integração/webhook
não reabrem atendimentos encerrados quando o texto contém algum termo informado pelo provedor.
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

CLOSED_STATUSES = frozenset(['closed', 'resolved', 'finalizada', 'encerrada', 'closing'])


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize('NFKD', (value or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_auto_resolve_keywords(raw: str | None) -> list[str]:
    if not raw or not str(raw).strip():
        return []
    items = []
    for line in str(raw).replace(';', '\n').splitlines():
        kw = _normalize_text(line)
        if kw:
            items.append(kw)
    return items


def auto_resolve_filter_enabled(provedor) -> bool:
    return bool(getattr(provedor, 'auto_resolve_keyword_filter_enabled', False))


def message_matches_auto_resolve_keywords(text: str, provedor) -> bool:
    if not auto_resolve_filter_enabled(provedor):
        return False
    keywords = parse_auto_resolve_keywords(getattr(provedor, 'auto_resolve_keywords', None))
    if not keywords:
        return False
    blob = _normalize_text(text)
    if not blob:
        return False
    return any(kw in blob for kw in keywords)


def should_suppress_reopen_for_auto_message(text: str, provedor) -> bool:
    return message_matches_auto_resolve_keywords(text, provedor)


def is_automated_outbound_message(message) -> bool:
    """Mensagem enviada pelo sistema (webhook de disparo, eco WhatsApp Business, template externo)."""
    if getattr(message, 'is_from_customer', True):
        return False
    attrs = getattr(message, 'additional_attributes', None) or {}
    if attrs.get('sgp_dispatch'):
        return True
    if str(attrs.get('sent_via') or '').strip() == 'inbound_webhook':
        return True
    if str(attrs.get('source') or '').strip() == 'whatsapp_business_app':
        return True
    return False


def keep_conversation_closed_after_auto_message(conversation, provedor, *, source: str = 'keyword_auto_resolve') -> None:
    from django.utils import timezone

    from conversations.closing_service import stamp_automation_closure_trace

    now = timezone.now()
    conversation.status = 'closed'
    conversation.assignee = None
    conversation.waiting_for_agent = False
    conversation.closing_requested_at = None
    conversation.updated_at = now
    conversation.save(
        update_fields=[
            'status',
            'assignee',
            'waiting_for_agent',
            'closing_requested_at',
            'updated_at',
        ]
    )
    try:
        stamp_automation_closure_trace(conversation, source)
    except Exception as exc:
        logger.warning(
            '[AutoResolve] Falha ao registrar trace conv=%s: %s',
            conversation.id,
            exc,
        )
    logger.info(
        '[AutoResolve] Conversa %s mantida encerrada (provedor=%s)',
        conversation.id,
        getattr(provedor, 'id', None),
    )


def maybe_auto_resolve_after_outbound_message(message) -> bool:
    """
    Após gravar mensagem automática de saída, mantém o atendimento encerrado
    se o texto contiver algum termo configurado pelo provedor.
    """
    conversation = getattr(message, 'conversation', None)
    if not conversation:
        return False
    inbox = getattr(conversation, 'inbox', None)
    provedor = getattr(inbox, 'provedor', None) if inbox else None
    if not provedor:
        return False
    if not is_automated_outbound_message(message):
        return False
    content = getattr(message, 'content', '') or ''
    if not should_suppress_reopen_for_auto_message(content, provedor):
        return False
    keep_conversation_closed_after_auto_message(
        conversation,
        provedor,
        source='keyword_auto_resolve_outbound',
    )
    return True
