"""
Handler para eventos de typing indicators (indicadores de digitação) do WhatsApp
"""
import logging
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from conversations.models import Conversation, Message
from core.models import Canal

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def process_typing_indicators(waba_id: str, events_data):
    """
    Processa eventos de typing indicators (indicadores de digitação) recebidos do WhatsApp.
    
    Os eventos de typing indicator vêm no campo "automatic_events" do webhook e indicam
    quando o cliente está digitando uma mensagem.
    
    Estrutura esperada dos eventos:
    [
        {
            "type": "message",
            "from": "5511999999999",
            "timestamp": "1234567890",
            "automatic_event": {
                "type": "typing_on" ou "typing_off"
            }
        }
    ]
    
    Args:
        waba_id: WhatsApp Business Account ID
        events_data: Lista de eventos de typing indicators (pode ser lista ou dict com metadata)
    """
    if not events_data:
        return
    
    # Se events_data é um dict, pode ter metadata e events
    if isinstance(events_data, dict):
        events = events_data.get("automatic_events", events_data.get("events", []))
    else:
        events = events_data
    
    if not events:
        return
    
    for event in events:
        try:
            event_type = event.get("type")
            if event_type != "message":
                continue
            
            # Verificar se é um evento de typing indicator
            # Os eventos de typing têm a estrutura:
            # {
            #   "type": "message",
            #   "from": "5511999999999",
            #   "timestamp": "1234567890",
            #   "automatic_event": {
            #     "type": "typing_on" ou "typing_off"
            #   }
            # }
            automatic_event = event.get("automatic_event", {})
            typing_type = automatic_event.get("type")
            
            if typing_type not in ["typing_on", "typing_off"]:
                continue
            
            from_number = event.get("from")
            timestamp = event.get("timestamp")
            
            if not from_number:
                continue
            
            # Buscar canal pelo waba_id
            canal = Canal.objects.filter(waba_id=waba_id, tipo="whatsapp_oficial", ativo=True).first()
            if not canal:
                logger.warning(f"[TypingIndicator] Canal não encontrado para waba_id {waba_id}")
                continue
            
            # Buscar conversa pelo número do cliente
            # Normalizar número (remover + se houver)
            normalized_number = from_number.replace("+", "")
            
            # Buscar contato e conversa
            from conversations.models import Contact, Inbox
            provedor = canal.provedor
            inbox = Inbox.objects.filter(provedor=provedor, channel_type="whatsapp").first()
            
            if not inbox:
                logger.warning(f"[TypingIndicator] Inbox não encontrado para provedor {provedor.id}")
                continue
            
            # Buscar contato pelo número
            contact = Contact.objects.filter(phone=normalized_number, provedor=provedor).first()
            if not contact:
                logger.debug(f"[TypingIndicator] Contato não encontrado para número {normalized_number}")
                continue
            
            # Buscar conversa ativa
            conversation = Conversation.objects.filter(
                contact=contact,
                inbox=inbox,
                status__in=["open", "pending"]
            ).order_by("-last_message_at").first()
            
            if not conversation:
                logger.debug(f"[TypingIndicator] Conversa não encontrada para contato {contact.id}")
                continue
            
            # Notificar frontend via WebSocket
            is_typing = typing_type == "typing_on"
            
            try:
                async_to_sync(channel_layer.group_send)(
                    f"conversation_{conversation.id}",
                    {
                        "type": "typing_indicator",
                        "conversation_id": conversation.id,
                        "is_typing": is_typing,
                        "from_number": from_number,
                        "timestamp": timestamp
                    }
                )
                logger.info(f"[TypingIndicator] Notificação enviada: conversation_id={conversation.id}, is_typing={is_typing}")
            except Exception as e:
                logger.error(f"[TypingIndicator] Erro ao enviar notificação WebSocket: {e}", exc_info=True)
                
        except Exception as e:
            logger.error(f"[TypingIndicator] Erro ao processar evento: {e}", exc_info=True)
            continue

