"""
Webhook do Banco Inter — atualiza cobranças e bloqueia/libera provedores.
"""
from __future__ import annotations

import json
import logging
import secrets

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from integrations.inter_config import get_inter_webhook_auth_token

from .billing_auto_block import sync_provedor_billing_block
from .inter_billing_service import sync_charge_from_webhook_payload

logger = logging.getLogger(__name__)


def _extract_token(request) -> str:
    received = (
        request.headers.get("x-inter-token")
        or request.headers.get("inter-webhook-token")
        or request.headers.get("Authorization")
        or request.META.get("HTTP_X_INTER_TOKEN")
        or request.META.get("HTTP_AUTHORIZATION")
        or ""
    ).strip()
    if received.lower().startswith("bearer "):
        received = received[7:].strip()
    # Query opcional (?token=)
    q = (request.GET.get("token") or "").strip()
    return received or q


@csrf_exempt
@require_http_methods(["GET", "HEAD", "POST"])
def inter_webhook(request):
    """
    POST /api/webhooks/inter/
    Callbacks de cobrança (pago / cancelado / expirado).
    """
    if request.method in ("GET", "HEAD"):
        return JsonResponse(
            {"status": "ok", "message": "NioHub superadmin Inter webhook online"},
            status=200,
        )

    expected = get_inter_webhook_auth_token()
    if expected:
        received = _extract_token(request)
        if not received or not secrets.compare_digest(received, expected):
            logger.warning("[InterWebhook] Token inválido")
            return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        body = {}

    # Inter pode enviar objeto único ou lista
    items = body if isinstance(body, list) else [body]
    updated = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            charge = sync_charge_from_webhook_payload(item)
            if charge:
                updated += 1
                try:
                    sync_provedor_billing_block(charge.provedor)
                except Exception:
                    logger.exception(
                        "[InterWebhook] Falha no auto-block provedor=%s",
                        charge.provedor_id,
                    )
        except Exception:
            logger.exception("[InterWebhook] Erro ao processar item")

    return JsonResponse({"ok": True, "updated": updated})
