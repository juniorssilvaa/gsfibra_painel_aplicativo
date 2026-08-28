"""Mapeia id central (superadmin) ↔ Provedor local no tenant (ids podem diferir)."""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def configured_central_provedor_id() -> Optional[int]:
    raw = ''
    try:
        from django.conf import settings

        raw = str(getattr(settings, 'SUPERADMIN_PROVEDOR_ID', '') or '').strip()
    except Exception:
        pass
    if not raw:
        raw = os.environ.get('SUPERADMIN_PROVEDOR_ID', '').strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def resolve_local_provedor_for_central_id(central_provedor_id) -> Optional['Provedor']:
    """
    Webhooks e sync do superadmin enviam o id central (ex.: 10).
    No tenant o mesmo provedor pode ser id local 6.
    """
    from core.models import Provedor

    if central_provedor_id is None:
        return None

    try:
        central_id = int(central_provedor_id)
    except (TypeError, ValueError):
        return None

    provedor = Provedor.objects.filter(id=central_id).first()
    if provedor:
        return provedor

    stack_central_id = configured_central_provedor_id()
    if stack_central_id is not None and stack_central_id == central_id:
        provedor = Provedor.objects.order_by('-id').first()
        if provedor:
            logger.debug(
                '[provedor_map] central_id=%s → local id=%s (SUPERADMIN_PROVEDOR_ID)',
                central_id,
                provedor.id,
            )
            return provedor

    count = Provedor.objects.count()
    if count == 1:
        provedor = Provedor.objects.first()
        logger.debug(
            '[provedor_map] central_id=%s → único local id=%s',
            central_id,
            provedor.id,
        )
        return provedor

    logger.warning(
        '[provedor_map] Provedor central id=%s não mapeado (count local=%s)',
        central_id,
        count,
    )
    return None
