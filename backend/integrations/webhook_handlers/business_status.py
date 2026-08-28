"""
Handler para eventos business_status_update (CRÍTICO)

Controla o status do canal WhatsApp (CONNECTED, DISCONNECTED, SUSPENDED, RESTRICTED)
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from core.models import Canal

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def process_business_status_update(waba_id: str, value: dict):
    """
    Processa atualizações de status do negócio (CRÍTICO).
    
    Exemplo de payload:
    {
        "business_id": "123456",
        "event": "DISCONNECTED"
    }
    
    Eventos possíveis:
    - CONNECTED: Canal conectado e operacional
    - DISCONNECTED: Canal desconectado
    - SUSPENDED: Canal suspenso
    - RESTRICTED: Canal com restrições
    """
    try:
        event = value.get("event")
        business_id = value.get("business_id")
        
        if not event:
            return
        
        # Localizar canal pelo waba_id
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal:
            return
        
        # Mapear evento da Meta para status do canal
        status_map = {
            "CONNECTED": "connected",
            "DISCONNECTED": "disconnected",
            "SUSPENDED": "suspended",
            "RESTRICTED": "restricted",
            "COMPROMISED_NOTIFICATION": "disconnected"  # Conta comprometida = desconectado
        }
        
        new_status = status_map.get(event, "disconnected")
        old_status = canal.status
        
        # Atualizar status do canal
        canal.status = new_status
        
        # Se desconectado/suspenso, marcar como inativo
        if event in ["DISCONNECTED", "SUSPENDED", "RESTRICTED"]:
            canal.ativo = False
        elif event == "CONNECTED":
            canal.ativo = True
        
        canal.save()
        
        # Emitir WebSocket para o provedor
        if canal.provedor:
            provedor_id = canal.provedor.id
            
            # Enviar evento via WebSocket
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"provedor_{provedor_id}",
                    {
                        "type": "channel_status_update",
                        "data": {
                            "canal_id": canal.id,
                            "canal_tipo": canal.tipo,
                            "waba_id": waba_id,
                            "status_anterior": old_status,
                            "status_novo": new_status,
                            "evento_meta": event,
                            "ativo": canal.ativo
                        }
                    }
                )
        
    except Exception as e:
        logger.error(f"[BusinessStatus] Erro ao processar business_status_update para waba_id {waba_id}: {str(e)}", exc_info=True)

