"""Origem de anúncio Click-to-WhatsApp nas mensagens recebidas pela Cloud API."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from django.db.models import Count, Max, Q
from django.utils import timezone

logger = logging.getLogger(__name__)

CONVERSATION_ATTR = 'ad_referral'
REPORT_DAYS = (7, 30, 90)
REPORT_MAX_ADS = 100


def _clean(value, max_len: Optional[int] = None) -> str:
    text = str(value or '').strip()
    return text[:max_len] if max_len else text


def record_ad_referral(*, provedor, contact, conversation, message_external_id, referral, new_contact=False):
    """Grava a entrada vinda de anúncio e marca a conversa com a origem (sem o ctwa_clid)."""
    from conversations.models import AdReferral, Conversation

    if not isinstance(referral, dict) or not message_external_id or conversation is None:
        return None
    source_id = _clean(referral.get('source_id'), 64)
    ctwa_clid = _clean(referral.get('ctwa_clid'), 512)
    if not source_id and not ctwa_clid:
        return None

    try:
        item, _ = AdReferral.objects.get_or_create(
            message_external_id=_clean(message_external_id, 255),
            defaults={
                'provedor': provedor,
                'contact': contact,
                'conversation': conversation,
                'source_type': _clean(referral.get('source_type'), 20),
                'source_id': source_id,
                'source_url': _clean(referral.get('source_url')),
                'headline': _clean(referral.get('headline'), 500),
                'body': _clean(referral.get('body')),
                'media_type': _clean(referral.get('media_type'), 20),
                'thumbnail_url': _clean(referral.get('thumbnail_url') or referral.get('image_url')),
                'ctwa_clid': ctwa_clid,
                'new_contact': bool(new_contact),
            },
        )
    except Exception as exc:
        logger.warning('[AdReferral] Falha ao gravar origem do anúncio (conversa %s): %s', conversation.pk, exc)
        return None

    attrs = dict(conversation.additional_attributes or {})
    attrs[CONVERSATION_ATTR] = {
        'referral_id': item.id,
        'source_type': item.source_type,
        'source_id': item.source_id,
        'source_url': item.source_url,
        'headline': item.headline,
        'body': item.body,
        'received_at': item.created_at.isoformat() if item.created_at else timezone.now().isoformat(),
    }
    Conversation.objects.filter(pk=conversation.pk).update(additional_attributes=attrs)
    conversation.additional_attributes = attrs
    return item


def ad_origin_for_prompt(conversation) -> Optional[Dict[str, str]]:
    """Resumo do anúncio que trouxe o cliente na sessão atual, para o contexto da IA."""
    if conversation is None:
        return None
    data = (conversation.additional_attributes or {}).get(CONVERSATION_ATTR)
    if not isinstance(data, dict):
        return None
    origin = {
        'tipo': 'publicacao' if data.get('source_type') == 'post' else 'anuncio',
        'titulo': _clean(data.get('headline'), 300),
        'texto': _clean(data.get('body'), 1000),
    }
    return origin if origin['titulo'] or origin['texto'] else {'tipo': origin['tipo']}


def ad_referral_report(provedor_id: int, days: int) -> Dict[str, Any]:
    from conversations.models import AdReferral

    since = timezone.now() - timedelta(days=days)
    qs = AdReferral.objects.filter(provedor_id=provedor_id, created_at__gte=since)

    summary = qs.aggregate(
        entries=Count('id'),
        contacts=Count('contact', distinct=True),
        new_contacts=Count('id', filter=Q(new_contact=True)),
        ads=Count('source_id', distinct=True),
    )

    rows = list(
        qs.values('source_id')
        .annotate(
            entries=Count('id'),
            contacts=Count('contact', distinct=True),
            new_contacts=Count('id', filter=Q(new_contact=True)),
            last_entry_at=Max('created_at'),
        )
        .order_by('-entries')[:REPORT_MAX_ADS]
    )

    wanted = {r['source_id'] for r in rows}
    latest: Dict[str, Dict[str, Any]] = {}
    details = qs.filter(source_id__in=wanted).order_by('-id').values(
        'source_id', 'source_type', 'source_url', 'headline', 'body', 'media_type', 'thumbnail_url'
    )
    for detail in details.iterator():
        latest.setdefault(detail['source_id'], detail)
        if len(latest) == len(wanted):
            break

    ads = []
    for row in rows:
        info = latest.get(row['source_id'], {})
        ads.append({
            'source_id': row['source_id'],
            'source_type': info.get('source_type') or '',
            'source_url': info.get('source_url') or '',
            'headline': info.get('headline') or '',
            'body': info.get('body') or '',
            'media_type': info.get('media_type') or '',
            'thumbnail_url': info.get('thumbnail_url') or '',
            'entries': row['entries'],
            'contacts': row['contacts'],
            'new_contacts': row['new_contacts'],
            'last_entry_at': row['last_entry_at'].isoformat() if row['last_entry_at'] else None,
        })

    return {
        'days': days,
        'summary': {key: summary.get(key) or 0 for key in ('entries', 'contacts', 'new_contacts', 'ads')},
        'ads': ads,
    }
