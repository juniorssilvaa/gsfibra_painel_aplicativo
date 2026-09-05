"""
Webhook do Asaas no superadmin — desbloqueia/bloqueia provedores ao confirmar pagamento.
"""
from __future__ import annotations

import json
import logging
import secrets

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from integrations.asaas_config import get_asaas_webhook_auth_token

from .billing_auto_block import sync_provedor_billing_block
from .models import Provedor

logger = logging.getLogger(__name__)

_PAYMENT_EVENTS = frozenset({
    'PAYMENT_CREATED',
    'PAYMENT_UPDATED',
    'PAYMENT_CONFIRMED',
    'PAYMENT_RECEIVED',
    'PAYMENT_RECEIVED_IN_CASH',
    'PAYMENT_OVERDUE',
    'PAYMENT_DELETED',
    'PAYMENT_RESTORED',
    'PAYMENT_REFUNDED',
    'PAYMENT_AWAITING_RISK_ANALYSIS',
    'PAYMENT_APPROVED_BY_RISK_ANALYSIS',
    'PAYMENT_REPROVED_BY_RISK_ANALYSIS',
})


def _extract_webhook_token(request) -> str:
    received = (
        request.headers.get('asaas-access-token')
        or request.headers.get('access_token')
        or request.headers.get('token')
        or request.headers.get('Authorization')
        or request.META.get('HTTP_ASAAS_ACCESS_TOKEN')
        or request.META.get('HTTP_ACCESS_TOKEN')
        or request.META.get('HTTP_TOKEN')
        or request.META.get('HTTP_AUTHORIZATION')
        or ''
    ).strip()
    if received.lower().startswith('bearer '):
        received = received[7:].strip()
    return received


def _find_provedor(payment: dict) -> Provedor | None:
    subscription_id = (payment.get('subscription') or '').strip()
    customer_id = (payment.get('customer') or '').strip()

    if subscription_id:
        prov = Provedor.objects.filter(asaas_subscription_id=subscription_id).first()
        if prov:
            return prov

    if customer_id:
        return Provedor.objects.filter(asaas_customer_id=customer_id).first()

    return None


@csrf_exempt
@require_http_methods(['GET', 'HEAD', 'POST'])
def asaas_webhook(request):
    """
    POST /api/webhooks/asaas/
    O Asaas envia eventos de cobrança (PAYMENT_RECEIVED, PAYMENT_CONFIRMED, etc.).
    """
    if request.method in ('GET', 'HEAD'):
        return JsonResponse(
            {'status': 'ok', 'message': 'NioHub superadmin Asaas webhook online'},
            status=200,
        )

    expected_token = get_asaas_webhook_auth_token()
    if not expected_token:
        logger.error('[AsaasWebhook] asaas_webhook_auth_token não configurado no SystemConfig.')
        return JsonResponse({'error': 'Webhook auth token não configurado'}, status=503)

    received_token = _extract_webhook_token(request)
    if not received_token or not secrets.compare_digest(received_token, expected_token):
        logger.warning('[AsaasWebhook] Token inválido ou ausente.')
        return JsonResponse({'error': 'Não autorizado'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    event = str(payload.get('event') or '').upper()
    payment = payload.get('payment') or {}

    if event and event not in _PAYMENT_EVENTS:
        return JsonResponse({'status': 'ignored', 'reason': 'event_not_handled', 'event': event}, status=200)

    if not payment:
        return JsonResponse({'status': 'ignored', 'reason': 'missing_payment'}, status=200)

    provedor = _find_provedor(payment)
    if not provedor:
        return JsonResponse(
            {
                'status': 'ignored',
                'reason': 'provider_not_found',
                'event': event,
                'subscription': payment.get('subscription'),
                'customer': payment.get('customer'),
            },
            status=200,
        )

    result = sync_provedor_billing_block(provedor)
    logger.info(
        '[AsaasWebhook] event=%s provedor=%s action=%s changed=%s',
        event,
        provedor.id,
        result.get('action'),
        result.get('changed'),
    )

    return JsonResponse(
        {
            'status': 'ok',
            'event': event,
            'provedor_id': provedor.id,
            'sync': result,
        },
        status=200,
    )
