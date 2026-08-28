"""
Webhook field `calls` — WhatsApp Cloud API (ligações).
"""
import logging
from typing import Any, Dict, List

from core.models import Canal
from integrations.niohub_voice_calls import VOICE_CALLS_EXTRAS_KEY
from integrations.whatsapp_calls import schedule_inbound_call_auto_reject


def _voice_calls_enabled(canal: Canal) -> bool:
    extras = getattr(canal, 'dados_extras', None) or {}
    if not isinstance(extras, dict):
        return False
    vc = extras.get(VOICE_CALLS_EXTRAS_KEY) or {}
    return bool(isinstance(vc, dict) and vc.get('enabled') and vc.get('session_id'))

logger = logging.getLogger(__name__)


def _resolve_canal_for_calls(waba_id: str, metadata: Dict[str, Any]) -> Canal | None:
    phone_number_id = (metadata.get('phone_number_id') or '').strip()
    qs = Canal.objects.filter(tipo='whatsapp_oficial', ativo=True)
    if phone_number_id:
        canal = qs.filter(phone_number_id=phone_number_id).first()
        if canal:
            return canal
    if waba_id:
        canal = qs.filter(waba_id=waba_id).first()
        if canal:
            return canal
    return None


def process_whatsapp_calls(waba_id: str, value: Dict[str, Any]) -> None:
    """
    Processa eventos do campo `calls` (connect, ringing, terminate, etc.).
    Quando configurado no canal, rejeita ligações recebidas e envia mensagem de aviso.
    """
    calls: List[Dict[str, Any]] = value.get('calls') or []
    if not calls:
        return

    metadata = value.get('metadata') or {}
    contacts = value.get('contacts') or []
    canal = _resolve_canal_for_calls(waba_id, metadata)
    if not canal:
        logger.warning(
            '[Webhook calls] Canal não encontrado waba_id=%s phone_number_id=%s',
            waba_id,
            metadata.get('phone_number_id'),
        )
        return

    for call in calls:
        if not isinstance(call, dict):
            continue
        event = (call.get('event') or '').lower()
        logger.info(
            '[Webhook calls] canal=%s event=%s call_id=%s from=%s to=%s direction=%s',
            canal.id,
            event,
            call.get('id'),
            call.get('from'),
            call.get('to'),
            call.get('direction'),
        )
        if event in ('connect', 'ringing'):
            if _voice_calls_enabled(canal):
                logger.info(
                    '[Webhook calls] Auto-reject ignorado — ligações por QR ativas no canal=%s',
                    canal.id,
                )
                continue
            schedule_inbound_call_auto_reject(canal, call, contacts)
