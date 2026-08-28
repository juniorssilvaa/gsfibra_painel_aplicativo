"""
Handler para eventos user_preferences

Processa preferências de usuários (ex: opt-out de mensagens de marketing)
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from core.models import Canal, Provedor
from conversations.models import Contact

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def process_user_preferences(waba_id: str, value: dict):
    """
    Processa preferências de usuários.
    
    Exemplo de payload:
    {
        "messaging_product": "whatsapp",
        "metadata": {
            "display_phone_number": "16505551111",
            "phone_number_id": "123456123"
        },
        "user_preferences": [
            {
                "wa_id": "16315551181",
                "detail": "User requested to stop marketing messages",
                "category": "marketing_messages",
                "value": "stop",
                "timestamp": 1729610285
            }
        ],
        "contacts": [...]
    }
    
    Categorias comuns:
    - marketing_messages: Opt-out de mensagens de marketing
    - utility_messages: Preferências de mensagens utilitárias
    """
    try:
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")
        user_preferences = value.get("user_preferences", [])
        contacts = value.get("contacts", [])
        
        # Localizar canal
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal or not canal.provedor:
            return
        
        provedor = canal.provedor
        
        # Processar cada preferência
        for pref in user_preferences:
            wa_id = pref.get("wa_id")
            category = pref.get("category")
            pref_value = pref.get("value")  # "stop" ou "start"
            detail = pref.get("detail", "")
            timestamp = pref.get("timestamp")
            
            if not wa_id:
                continue
            
            # Normalizar número de telefone
            normalized_phone = wa_id.replace("+", "").replace(" ", "").replace("-", "")
            
            # Atualizar contato
            contact, _ = Contact.objects.get_or_create(
                phone=normalized_phone,
                provedor=provedor,
                defaults={"name": normalized_phone}
            )
            
            # Se for opt-out de marketing, marcar contato
            if category == "marketing_messages" and pref_value == "stop":
                # Opcional: adicionar flag no contato
                # contact.opt_out_marketing = True
                # contact.save()
                pass
        
        # Emitir WebSocket para notificar admins sobre opt-outs importantes
        if channel_layer and any(
            p.get("category") == "marketing_messages" and p.get("value") == "stop"
            for p in user_preferences
        ):
            async_to_sync(channel_layer.group_send)(
                f"provedor_{provedor.id}",
                {
                    "type": "user_preferences_update",
                    "data": {
                        "waba_id": waba_id,
                        "phone_number_id": phone_number_id,
                        "preferences_count": len(user_preferences),
                        "has_opt_outs": True
                    }
                }
            )
        
    except Exception as e:
        pass

