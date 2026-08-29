"""
Handler para account_update (desconexão / remoção do app parceiro).
"""
import logging

from integrations.whatsapp_oficial_status import (
    DISCONNECT_ACCOUNT_EVENTS,
    find_whatsapp_oficial_canal,
    mark_whatsapp_oficial_disconnected,
)

logger = logging.getLogger(__name__)


def process_account_update(waba_id: str, value: dict):
    """
    Processa account_update da Meta.

    Eventos relevantes (não exaustivo):
    - PARTNER_APP_UNINSTALLED
    - PARTNER_REMOVED
    - ACCOUNT_DELETED / ACCOUNT_VIOLATION / DISABLED_UPDATE
    """
    try:
        event = (value.get('event') or value.get('type') or '').strip().upper()
        phone_number_id = (
            value.get('phone_number_id')
            or (value.get('metadata') or {}).get('phone_number_id')
        )

        if not event:
            logger.info('[AccountUpdate] Payload sem event waba=%s value=%s', waba_id, value)
            return

        # Alguns updates não são disconnect (ex.: VERIFIED_ACCOUNT)
        if event not in DISCONNECT_ACCOUNT_EVENTS and 'UNINSTALL' not in event and 'REMOVED' not in event:
            # BAN / DISABLED variants
            if not any(x in event for x in ('DISABLE', 'DELETE', 'VIOLATION', 'BAN', 'RESTRICT')):
                logger.info('[AccountUpdate] Evento ignorado waba=%s event=%s', waba_id, event)
                return

        canal = find_whatsapp_oficial_canal(waba_id=waba_id, phone_number_id=phone_number_id)
        if not canal:
            logger.info(
                '[AccountUpdate] Nenhum canal waba=%s phone=%s event=%s',
                waba_id,
                phone_number_id,
                event,
            )
            return

        mark_whatsapp_oficial_disconnected(
            canal,
            reason=f'account_update_{event}',
            event=event,
            status='disconnected',
        )
        logger.warning(
            '[AccountUpdate] Canal %s marcado desconectado por %s',
            canal.id,
            event,
        )
    except Exception as e:
        logger.error(
            '[AccountUpdate] Erro waba=%s: %s',
            waba_id,
            e,
            exc_info=True,
        )
