"""
Handlers para eventos de templates (OPCIONAL)

Suporta:
- message_template_components_update
- message_template_quality_update
- message_template_status_update
- template_category_update
- template_correct_category_detection
"""
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from core.models import Canal

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def process_template_components_update(waba_id: str, value: dict):
    """
    Processa atualizações de componentes de templates (OPCIONAL).
    
    Exemplo de payload completo:
    {
        "message_template_id": 12345678,
        "message_template_name": "my_message_template",
        "message_template_language": "en-US",
        "message_template_title": "message header",
        "message_template_element": "message body",
        "message_template_footer": "message footer",
        "message_template_buttons": [
            {
                "message_template_button_type": "URL",
                "message_template_button_text": "button text",
                "message_template_button_url": "https://example.com",
                "message_template_button_phone_number": "12342342345"
            }
        ]
    }
    
    Ações:
    - Se houver painel de templates: atualizar/sincronizar no banco
    - Emitir WebSocket leve para atualizar UI
    - Se não houver uso de templates: apenas ACK 200
    """
    try:
        template_id = value.get("message_template_id")
        template_name = value.get("message_template_name")
        template_language = value.get("message_template_language")
        template_title = value.get("message_template_title")
        template_element = value.get("message_template_element")
        template_footer = value.get("message_template_footer")
        template_buttons = value.get("message_template_buttons", [])
        
        # Localizar canal para identificar o provedor
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal or not canal.provedor:
            return
        
        provedor_id = canal.provedor.id
        
        # Opcional: Atualizar template no banco (se houver modelo)
        # Template.objects.update_or_create(
        #     template_id=template_id,
        #     provedor=canal.provedor,
        #     defaults={
        #         "name": template_name,
        #         "language": template_language,
        #         "title": template_title,
        #         "element": template_element,
        #         "footer": template_footer,
        #         "buttons": template_buttons,
        #         "updated_at": timezone.now()
        #     }
        # )
        
        # Emitir WebSocket leve para atualizar UI
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"provedor_{provedor_id}",
                {
                    "type": "template_update",
                    "data": {
                        "waba_id": waba_id,
                        "template_id": template_id,
                        "template_name": template_name,
                        "template_language": template_language,
                        "template_title": template_title,
                        "template_element": template_element,
                        "template_footer": template_footer,
                        "template_buttons": template_buttons,
                        "buttons_count": len(template_buttons)
                    }
                }
            )
        
    except Exception as e:
        pass


def process_template_quality_update(waba_id: str, value: dict):
    """
    Processa atualizações de qualidade de templates.
    
    Exemplo de payload:
    {
        "previous_quality_score": "GREEN",
        "new_quality_score": "YELLOW",
        "message_template_id": 12345678,
        "message_template_name": "my_template",
        "message_template_language": "pt-BR"
    }
    """
    try:
        template_id = value.get("message_template_id")
        template_name = value.get("message_template_name")
        previous_score = value.get("previous_quality_score")
        new_score = value.get("new_quality_score")
        
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal or not canal.provedor:
            return
        
        provedor_id = canal.provedor.id
        
        # Emitir WebSocket se qualidade piorou
        if new_score in ["YELLOW", "RED"] and channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"provedor_{provedor_id}",
                {
                    "type": "template_quality_alert",
                    "data": {
                        "waba_id": waba_id,
                        "template_id": template_id,
                        "template_name": template_name,
                        "previous_score": previous_score,
                        "new_score": new_score,
                        "requires_attention": True
                    }
                }
            )
        
    except Exception as e:
        pass


def process_template_status_update(waba_id: str, value: dict):
    """
    Processa atualizações de status de templates.
    
    Exemplo de payload:
    {
        "event": "APPROVED" | "REJECTED" | "PENDING",
        "message_template_id": 12345678,
        "message_template_name": "my_template",
        "message_template_language": "pt-BR",
        "reason": null,
        "message_template_category": "MARKETING"
    }
    """
    try:
        template_id = value.get("message_template_id")
        template_name = value.get("message_template_name")
        event = value.get("event")
        reason = value.get("reason")
        category = value.get("message_template_category")
        
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal or not canal.provedor:
            return
        
        provedor_id = canal.provedor.id
        
        # Emitir WebSocket para atualizar UI
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"provedor_{provedor_id}",
                {
                    "type": "template_status_update",
                    "data": {
                        "waba_id": waba_id,
                        "template_id": template_id,
                        "template_name": template_name,
                        "status": event,
                        "category": category,
                        "reason": reason,
                        "requires_action": event == "REJECTED"
                    }
                }
            )
        
    except Exception as e:
        pass


def process_template_category_update(waba_id: str, value: dict):
    """
    Processa atualizações de categoria de templates.
    
    Exemplo de payload:
    {
        "message_template_id": 12345678,
        "message_template_name": "my_template",
        "previous_category": "MARKETING",
        "new_category": "UTILITY",
        "correct_category": "MARKETING",
        "category_appeal_status": "ELIGIBLE"
    }
    """
    try:
        template_id = value.get("message_template_id")
        previous_category = value.get("previous_category")
        new_category = value.get("new_category")
        correct_category = value.get("correct_category")
        appeal_status = value.get("category_appeal_status")
        
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal or not canal.provedor:
            return
        
        provedor_id = canal.provedor.id
        
        # Emitir WebSocket se categoria mudou incorretamente
        if new_category != correct_category and channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"provedor_{provedor_id}",
                {
                    "type": "template_category_mismatch",
                    "data": {
                        "waba_id": waba_id,
                        "template_id": template_id,
                        "new_category": new_category,
                        "correct_category": correct_category,
                        "appeal_status": appeal_status,
                        "requires_review": True
                    }
                }
            )
        
    except Exception as e:
        pass


def process_template_correct_category_detection(waba_id: str, value: dict):
    """
    Processa detecção de categoria correta de templates.
    
    Exemplo de payload:
    {
        "message_template_id": 12345678,
        "message_template_name": "my_template",
        "category": "UTILITY",
        "correct_category": "MARKETING"
    }
    """
    try:
        template_id = value.get("message_template_id")
        category = value.get("category")
        correct_category = value.get("correct_category")
        
        # Apenas logar - não requer ação imediata
        # Pode ser usado para analytics ou notificações informativas
        
    except Exception as e:
        pass

