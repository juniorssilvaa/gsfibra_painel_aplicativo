"""
Contagem local de templates enviados por categoria (fallback quando Meta
não devolve pricing_analytics / conversation_analytics).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def count_template_sends_by_category(
    canal,
    *,
    start_ts: int,
    end_ts: int,
) -> List[Dict[str, Any]]:
    """
    Agrupa mensagens locais is_template=True pelo category do template na Meta.
    """
    try:
        from conversations.models import Message
        from integrations.whatsapp_templates import list_message_templates
    except Exception as exc:
        logger.info("[WA rates] imports falharam: %s", exc)
        return []

    start_dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)

    # Mapa nome_template → category
    name_to_cat: Dict[str, str] = {}
    try:
        ok, templates, _err = list_message_templates(canal, limit=250)
        if ok and templates:
            for t in templates:
                name = (t.get("name") or "").strip().lower()
                cat = (t.get("category") or "UTILITY").strip().upper()
                if name:
                    name_to_cat[name] = cat
    except Exception as exc:
        logger.info("[WA rates] list templates falhou: %s", exc)

    provedor_id = getattr(canal, "provedor_id", None)
    qs = Message.objects.filter(
        is_from_customer=False,
        created_at__gte=start_dt,
        created_at__lte=end_dt,
        additional_attributes__is_template=True,
    )
    if provedor_id:
        qs = qs.filter(conversation__inbox__provedor_id=provedor_id)
    # Inbox.channel_id costuma guardar o id do Canal
    qs_canal = qs.filter(conversation__inbox__channel_id=str(canal.id))
    if qs_canal.exists():
        qs = qs_canal

    buckets: Dict[str, int] = {}
    for attrs in qs.values_list("additional_attributes", flat=True).iterator(chunk_size=500):
        if not isinstance(attrs, dict):
            continue
        tname = (attrs.get("template_name") or "").strip().lower()
        cat = (attrs.get("template_category") or name_to_cat.get(tname) or "UTILITY").upper()
        if cat in ("TEMPLATES", "SESSION", "SERVICE"):
            cat = "UTILITY"
        buckets[cat] = buckets.get(cat, 0) + 1

    from integrations.whatsapp_pricing_rates import CATEGORY_LABELS

    rows = []
    for key, volume in sorted(buckets.items(), key=lambda x: -x[1]):
        rows.append(
            {
                "key": key,
                "label": CATEGORY_LABELS.get(key, key.title()),
                "volume": volume,
                "cost": 0.0,
            }
        )
    return rows
