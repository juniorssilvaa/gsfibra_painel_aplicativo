"""
Handler para eventos business_status_update (CRÍTICO)

Controla o status do canal WhatsApp (CONNECTED, DISCONNECTED, SUSPENDED, RESTRICTED)
"""
import logging

from integrations.whatsapp_oficial_status import (
    find_whatsapp_oficial_canal,
    mark_whatsapp_oficial_connected,
    mark_whatsapp_oficial_disconnected,
)

logger = logging.getLogger(__name__)


def process_business_status_update(waba_id: str, value: dict):
    """
    Processa atualizações de status do negócio (CRÍTICO).

    Eventos possíveis:
    - CONNECTED / DISCONNECTED / SUSPENDED / RESTRICTED / COMPROMISED_NOTIFICATION
    """
    try:
        event = (value.get('event') or '').strip().upper()
        if not event:
            return

        phone_number_id = (
            value.get('phone_number_id')
            or (value.get('metadata') or {}).get('phone_number_id')
        )
        canal = find_whatsapp_oficial_canal(
            waba_id=waba_id,
            phone_number_id=phone_number_id,
        )
        if not canal:
            logger.info(
                '[BusinessStatus] Nenhum canal para waba=%s phone=%s event=%s',
                waba_id,
                phone_number_id,
                event,
            )
            return

        if event == 'CONNECTED':
            mark_whatsapp_oficial_connected(canal, reason='business_status_CONNECTED')
            return

        status_map = {
            'DISCONNECTED': 'disconnected',
            'SUSPENDED': 'suspended',
            'RESTRICTED': 'restricted',
            'COMPROMISED_NOTIFICATION': 'disconnected',
        }
        new_status = status_map.get(event, 'disconnected')
        mark_whatsapp_oficial_disconnected(
            canal,
            reason=f'business_status_{event}',
            event=event,
            status=new_status,
        )
    except Exception as e:
        logger.error(
            '[BusinessStatus] Erro ao processar business_status_update waba=%s: %s',
            waba_id,
            e,
            exc_info=True,
        )
