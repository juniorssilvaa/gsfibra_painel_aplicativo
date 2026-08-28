"""
WhatsApp Cloud API — Calling (ligações).

Rejeição automática de ligações recebidas + mensagem de aviso ao cliente.
Configuração por canal em dados_extras:
  - calls_auto_reject_enabled (bool)
  - calls_auto_reject_message (str)
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, Optional, Tuple

import requests
from django.core.cache import cache

from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION

logger = logging.getLogger(__name__)

DEFAULT_CALLS_REJECT_MESSAGE = (
    'Este número não recebe ligações pelo WhatsApp. '
    'Por favor, envie uma mensagem de texto que teremos prazer em ajudar.'
)

_CALL_DEDUPE_TTL = 120


def get_calls_auto_reject_config(canal) -> Tuple[bool, str]:
    extras = getattr(canal, 'dados_extras', None) or {}
    if not isinstance(extras, dict):
        extras = {}
    enabled = bool(extras.get('calls_auto_reject_enabled'))
    message = (extras.get('calls_auto_reject_message') or '').strip()
    if not message:
        message = DEFAULT_CALLS_REJECT_MESSAGE
    return enabled, message[:4096]


def _normalize_wa_phone(raw: Any) -> str:
    digits = re.sub(r'\D', '', str(raw or ''))
    return digits


def reject_whatsapp_call(phone_number_id: str, token: str, call_id: str) -> Tuple[bool, Optional[str]]:
    if not phone_number_id or not token or not call_id:
        return False, 'phone_number_id, token ou call_id ausente'
    url = f'https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{phone_number_id}/calls'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    payload = {
        'messaging_product': 'whatsapp',
        'call_id': call_id,
        'action': 'reject',
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json() if resp.text else {}
            if data.get('success') is True or resp.ok:
                return True, None
        err = (resp.text or '')[:500]
        logger.warning(
            '[WhatsAppCalls] reject falhou call_id=%s status=%s body=%s',
            call_id,
            resp.status_code,
            err,
        )
        return False, err or f'HTTP {resp.status_code}'
    except Exception as exc:
        logger.error('[WhatsAppCalls] reject erro call_id=%s: %s', call_id, exc)
        return False, str(exc)


def send_calls_reject_notice(
    phone_number_id: str,
    token: str,
    to_wa_id: str,
    body: str,
) -> bool:
    from integrations.billing_reminder_service import _send_whatsapp_text

    phone = _normalize_wa_phone(to_wa_id)
    if not phone:
        return False
    return _send_whatsapp_text(phone_number_id, token, phone, body)


def _is_inbound_user_call(call: Dict[str, Any]) -> bool:
    direction = (call.get('direction') or '').upper()
    if direction == 'BUSINESS_INITIATED':
        return False
    if direction == 'USER_INITIATED':
        return True
    event = (call.get('event') or '').lower()
    return event in ('connect', 'ringing')


def handle_inbound_call_auto_reject(canal, call: Dict[str, Any], contacts: list) -> None:
    """
    Rejeita ligação recebida (se habilitado) e envia mensagem de texto ao cliente.
    Executar em thread — webhook deve responder 200 rápido.
    """
    enabled, message = get_calls_auto_reject_config(canal)
    if not enabled:
        logger.debug('[WhatsAppCalls] Auto-reject desligado canal=%s', canal.id)
        return

    if not _is_inbound_user_call(call):
        return

    call_id = (call.get('id') or '').strip()
    if not call_id:
        return

    dedupe_key = f'wa_call_reject:{canal.id}:{call_id}'
    if cache.get(dedupe_key):
        return
    cache.set(dedupe_key, '1', _CALL_DEDUPE_TTL)

    phone_number_id = (canal.phone_number_id or '').strip()
    token = (canal.token or '').strip()
    if not phone_number_id or not token:
        logger.warning('[WhatsAppCalls] Canal %s sem phone_number_id/token para rejeitar ligação', canal.id)
        return

    caller = _normalize_wa_phone(call.get('from'))
    if not caller and contacts:
        for c in contacts:
            wa = (c.get('wa_id') or '').strip()
            if wa:
                caller = _normalize_wa_phone(wa)
                break
    if not caller:
        logger.warning('[WhatsAppCalls] Sem número do chamador call_id=%s', call_id)
        return

    ok_reject, err_reject = reject_whatsapp_call(phone_number_id, token, call_id)
    if ok_reject:
        logger.info(
            '[WhatsAppCalls] Ligação rejeitada canal=%s call_id=%s from=%s',
            canal.id,
            call_id,
            caller,
        )
    else:
        logger.warning(
            '[WhatsAppCalls] Falha ao rejeitar canal=%s call_id=%s: %s',
            canal.id,
            call_id,
            err_reject,
        )

    if message:
        sent = send_calls_reject_notice(phone_number_id, token, caller, message)
        if sent:
            logger.info('[WhatsAppCalls] Aviso pós-ligação enviado canal=%s to=%s', canal.id, caller)
        else:
            logger.warning('[WhatsAppCalls] Falha ao enviar aviso pós-ligação canal=%s to=%s', canal.id, caller)


def schedule_inbound_call_auto_reject(canal, call: Dict[str, Any], contacts: list) -> None:
    threading.Thread(
        target=handle_inbound_call_auto_reject,
        args=(canal, call, contacts),
        daemon=True,
    ).start()
