"""
Handler para eventos account_alerts (IMPORTANTE)

Recebe alertas e riscos da conta WhatsApp Business
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from core.models import Canal

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def process_account_alerts(waba_id: str, value: dict):
    """
    Processa alertas da conta (IMPORTANTE).
    
    Exemplo de payload:
    {
        "entity_type": "WABA",
        "entity_id": "123456",
        "alert_severity": "CRITICAL",
        "alert_type": "OBA_APPROVED",
        "alert_description": "Sua conta foi aprovada"
    }
    
    Severidades:
    - CRITICAL: Requer ação imediata
    - HIGH: Requer atenção
    - MEDIUM: Informativo importante
    - LOW: Informativo
    - INFORMATIONAL: Apenas informativo
    """
    try:
        entity_type = value.get("entity_type")
        entity_id = value.get("entity_id")
        alert_severity = value.get("alert_severity", "INFORMATIONAL")
        alert_type = value.get("alert_type")
        alert_description = value.get("alert_description", "")
        
        # NÃO alterar status do canal automaticamente
        # Apenas notificar admins se for crítico
        
        # Localizar canal para identificar o provedor
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal or not canal.provedor:
            return
        
        provedor_id = canal.provedor.id
        
        # Se não for apenas informativo, emitir WebSocket para admins
        if alert_severity != "INFORMATIONAL":
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"provedor_{provedor_id}",
                    {
                        "type": "account_alert",
                        "data": {
                            "waba_id": waba_id,
                            "canal_id": canal.id,
                            "entity_type": entity_type,
                            "entity_id": entity_id,
                            "alert_severity": alert_severity,
                            "alert_type": alert_type,
                            "alert_description": alert_description,
                            "requires_action": alert_severity in ["CRITICAL", "HIGH"]
                        }
                    }
                )
        
        # Opcional: Salvar alerta no banco (se houver modelo para isso)
        # Alert.objects.create(
        #     provedor=canal.provedor,
        #     canal=canal,
        #     severity=alert_severity,
        #     alert_type=alert_type,
        #     description=alert_description,
        #     meta_data=value
        # )
        
    except Exception as e:
        logger.error(f"[AccountAlerts] Erro ao processar account_alerts para waba_id {waba_id}: {str(e)}", exc_info=True)

