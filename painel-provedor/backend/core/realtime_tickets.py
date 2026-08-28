"""
Tickets de curta duração para WebSocket / SSE.

Evita colocar o token DRF de longa duração em query strings (logs, proxy, Referer).
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing

logger = logging.getLogger(__name__)

REALTIME_TICKET_SALT = "niohub-realtime-ws"
REALTIME_TICKET_PURPOSE = "realtime"


def realtime_ticket_max_age() -> int:
    return int(getattr(settings, "REALTIME_TICKET_MAX_AGE", 90))


def issue_realtime_ticket(user) -> dict:
    """Emite ticket assinado para o usuário autenticado."""
    max_age = realtime_ticket_max_age()
    ticket = signing.dumps(
        {"uid": user.id, "pur": REALTIME_TICKET_PURPOSE},
        salt=REALTIME_TICKET_SALT,
    )
    return {"ticket": ticket, "expires_in": max_age}


def user_from_realtime_ticket(ticket: str):
    """Resolve usuário ativo a partir do ticket. Retorna None se inválido/expirado."""
    if not ticket:
        return None
    try:
        payload = signing.loads(
            ticket,
            salt=REALTIME_TICKET_SALT,
            max_age=realtime_ticket_max_age(),
        )
    except signing.SignatureExpired:
        logger.debug("Realtime ticket expirado")
        return None
    except signing.BadSignature:
        logger.debug("Realtime ticket inválido")
        return None

    if payload.get("pur") != REALTIME_TICKET_PURPOSE:
        return None

    user_id = payload.get("uid")
    if not user_id:
        return None

    User = get_user_model()
    try:
        return User.objects.get(pk=user_id, is_active=True)
    except User.DoesNotExist:
        return None


def allow_legacy_token_query() -> bool:
    """Por padrão NÃO aceita token DRF longo na query (máxima segurança)."""
    return bool(getattr(settings, "REALTIME_ALLOW_LEGACY_TOKEN_QUERY", False))
