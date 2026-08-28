"""
Handler para eventos de statuses de mensagens (IMPORTANTE)

Processa atualizações de status de mensagens enviadas:
- sent: Mensagem enviada
- delivered: Mensagem entregue ao destinatário
- read: Mensagem lida pelo destinatário
- failed: Falha ao enviar mensagem
"""
import json
import logging
from datetime import datetime
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from conversations.models import Message
from core.models import Canal

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


def process_message_statuses(waba_id: str, value: dict):
    """
    Processa atualizações de status de mensagens enviadas.
    
    Exemplo de payload:
    {
        "metadata": {
            "phone_number_id": "123456789"
        },
        "statuses": [
            {
                "id": "wamid.HBgNMTIzNDU2Nzg5MDEyMzQ1NgIBARgB",
                "status": "read",
                "timestamp": "1234567890",
                "recipient_id": "5511999999999",
                "conversation": {
                    "id": "conversation_id",
                    "origin": {
                        "type": "user_initiated"
                    }
                },
                "pricing": {
                    "billable": true,
                    "pricing_model": "CBP",
                    "category": "user_initiated"
                }
            }
        ]
    }
    
    Status possíveis:
    - sent: Mensagem enviada com sucesso
    - delivered: Mensagem entregue ao destinatário
    - read: Mensagem lida pelo destinatário
    - failed: Falha ao enviar mensagem
    """
    try:
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")
        statuses = value.get("statuses", [])
        
        if not statuses:
            return
        
        # Buscar canal pelo phone_number_id ou waba_id
        canal = None
        if phone_number_id:
            canal = Canal.objects.filter(
                tipo="whatsapp_oficial",
                phone_number_id=phone_number_id,
                ativo=True
            ).first()
        
        if not canal and waba_id:
            canal = Canal.objects.filter(
                tipo="whatsapp_oficial",
                waba_id=waba_id,
                ativo=True
            ).first()
        
        if not canal:
            logger.warning(f"Canal não encontrado para statuses: phone_number_id={phone_number_id}, waba_id={waba_id}")
            return
        
        # Processar cada status
        for idx, status_data in enumerate(statuses):
            message_id = status_data.get("id")  # ID da mensagem no WhatsApp (wamid)
            status = status_data.get("status")  # sent, delivered, read, failed
            timestamp = status_data.get("timestamp")
            recipient_id = status_data.get("recipient_id")
            
            if not message_id or not status:
                continue
            
            # Buscar a mensagem pelo external_id
            # O external_id pode estar no campo external_id OU em additional_attributes['external_id']
            message = Message.objects.filter(
                external_id=message_id,
                is_from_customer=False  # Apenas mensagens enviadas pelo agente
            ).first()
            
            # Se não encontrou no campo external_id, buscar em additional_attributes
            if not message:
                # Buscar mensagens recentes (última hora) e verificar additional_attributes
                from django.db.models import Q
                recent_messages = Message.objects.filter(
                    is_from_customer=False,
                    created_at__gte=timezone.now() - timezone.timedelta(hours=1)
                ).order_by('-created_at')[:20]
                
                for msg in recent_messages:
                    # Verificar se o external_id está em additional_attributes
                    attrs = msg.additional_attributes or {}
                    if attrs.get('external_id') == message_id:
                        message = msg
                        break
                    # Também verificar se está no campo external_id
                    if msg.external_id == message_id:
                        message = msg
                        break
            
            if not message:
                continue
            
            # Garantir que o external_id esteja no campo correto para futuras buscas
            if not message.external_id and message.additional_attributes:
                external_id_from_attrs = message.additional_attributes.get('external_id')
                if external_id_from_attrs:
                    message.external_id = external_id_from_attrs
                    message.save(update_fields=['external_id'])
            
            # Atualizar additional_attributes com o status
            additional_attrs = message.additional_attributes or {}
            
            # Converter timestamp para datetime se necessário
            status_timestamp = None
            if timestamp:
                try:
                    status_timestamp = datetime.fromtimestamp(int(timestamp))
                except (ValueError, TypeError):
                    status_timestamp = timezone.now()
            else:
                status_timestamp = timezone.now()
            
            # Atualizar status da mensagem
            status_history = additional_attrs.get("status_history", [])
            status_history.append({
                "status": status,
                "timestamp": status_timestamp.isoformat(),
                "recipient_id": recipient_id
            })
            
            additional_attrs["status_history"] = status_history
            additional_attrs["last_status"] = status
            additional_attrs["last_status_timestamp"] = status_timestamp.isoformat()
            
            # Adicionar informações específicas por status
            if status == "read":
                additional_attrs["read_at"] = status_timestamp.isoformat()
                additional_attrs["read_by"] = recipient_id
            elif status == "delivered":
                additional_attrs["delivered_at"] = status_timestamp.isoformat()
            elif status == "sent":
                additional_attrs["sent_at"] = status_timestamp.isoformat()
            elif status == "failed":
                error_data = status_data.get("errors", [])
                if error_data:
                    error_info = error_data[0] if error_data else None
                    additional_attrs["delivery_error"] = error_info
                    
                    # Extrair código de erro e traduzir mensagem
                    if isinstance(error_info, dict):
                        error_code = error_info.get("code")
                        error_message = error_info.get("message", "")
                        error_subcode = error_info.get("error_subcode")
                        
                        if error_code:
                            additional_attrs["delivery_error_code"] = error_code
                            
                            # Traduzir mensagem de erro usando função do sistema
                            try:
                                from integrations.whatsapp_cloud_send import translate_whatsapp_error
                                translated_error = translate_whatsapp_error(error_code, error_subcode, error_message)
                                additional_attrs["delivery_error_message"] = translated_error
                                
                                # Log específico para erro 131047 (24 horas)
                                if error_code == 131047:
                                    logger.warning(
                                        f"[MessageStatuses] ERRO 131047 detectado no webhook: "
                                        f"message_id={message_id}, error_code={error_code}, "
                                        f"translated={translated_error}"
                                    )
                            except Exception as e:
                                logger.error(f"[MessageStatuses] Erro ao traduzir mensagem de erro: {str(e)}")
                                additional_attrs["delivery_error_message"] = error_message
            
            message.additional_attributes = additional_attrs
            message.save(update_fields=['additional_attributes'])
            
            # Emitir evento WebSocket para atualizar o frontend
            if message.conversation and channel_layer:
                try:
                    ws_data = {
                        "type": "message_status_update",
                        "message_id": message.id,
                        "status": status,
                        "timestamp": status_timestamp.isoformat(),
                        "recipient_id": recipient_id
                    }
                    
                    # Incluir informações de erro se o status for "failed"
                    if status == "failed" and additional_attrs.get("delivery_error_code"):
                        ws_data["error_code"] = additional_attrs.get("delivery_error_code")
                        ws_data["error_message"] = additional_attrs.get("delivery_error_message", "")
                    
                    async_to_sync(channel_layer.group_send)(
                        f"conversation_{message.conversation.id}",
                        ws_data
                    )
                except Exception as ws_error:
                    logger.error(f"[MessageStatuses] Erro ao enviar WebSocket: {ws_error}", exc_info=True)
    
    except Exception as e:
        logger.error(f"[MessageStatuses] Erro ao processar statuses de mensagens: {str(e)}", exc_info=True)

