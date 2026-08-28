import json
from datetime import datetime
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class ConversationNotificationService:
    """
    Serviço para notificar mudanças de conversas via WebSocket
    Thread-safe e com tratamento adequado de erros
    """

    @staticmethod
    def _conversation_realtime_queryset():
        from django.db.models import Prefetch
        from .models import Conversation, Message

        return Conversation.objects.select_related(
            'contact', 'assignee', 'inbox', 'inbox__provedor', 'team'
        ).prefetch_related(
            Prefetch(
                'messages',
                queryset=Message.objects.order_by('-created_at')[:1],
                to_attr='last_message_prefetched',
            ),
        )

    @classmethod
    def serialize_conversation_realtime(cls, conversation_or_id):
        """Payload leve para WS (sem histórico completo de mensagens)."""
        from .serializers import ConversationListSerializer

        if isinstance(conversation_or_id, int):
            conversation_or_id = cls._conversation_realtime_queryset().get(id=conversation_or_id)
        return ConversationListSerializer(conversation_or_id).data

    @staticmethod
    def notify_conversation_updated(
        provedor_id,
        conversation_id,
        event_type,
        data=None,
        conversation_data=None,
    ):
        """
        Notifica mudança de conversa para todos os clientes do painel via WebSocket
        """
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return

            payload = conversation_data
            if payload is None:
                data_conversation = (data or {}).get('conversation')
                if isinstance(data_conversation, dict) and data_conversation.get('id'):
                    payload = data_conversation
            if payload is None:
                try:
                    payload = ConversationNotificationService.serialize_conversation_realtime(
                        conversation_id
                    )
                except Exception:
                    payload = None

            group_name = f'painel_{provedor_id}'

            event_data = {
                'type': 'conversation_event',
                'event_type': event_type,
                'conversation_id': conversation_id,
                'conversation': payload,
                'data': data or {},
                'timestamp': datetime.now().isoformat()
            }

            async_to_sync(channel_layer.group_send)(
                group_name,
                event_data
            )

            dashboard_group = f'dashboard_{provedor_id}'
            async_to_sync(channel_layer.group_send)(
                dashboard_group,
                {
                    'type': 'dashboard_stats_update'
                }
            )

        except Exception:
            pass
    @staticmethod
    def notify_conversation_closed(provedor_id, conversation_id):
        """
        Notifica que uma conversa foi encerrada
        """
        ConversationNotificationService.notify_conversation_updated(
            provedor_id, 
            conversation_id, 
            'conversation_closed',
            {'status': 'closed'}
        )
    
    @staticmethod
    def notify_conversation_ended(provedor_id, conversation_id):
        """
        Notifica que uma conversa foi encerrada por humano
        """
        ConversationNotificationService.notify_conversation_updated(
            provedor_id, 
            conversation_id, 
            'conversation_ended',
            {'status': 'ended'}
        )
    
    @staticmethod
    def notify_conversation_assigned(provedor_id, conversation_id, assignee_id):
        """
        Notifica que uma conversa foi atribuída
        
        Args:
            provedor_id: ID do provedor
            conversation_id: ID da conversa
            assignee_id: ID do usuário que recebeu a atribuição
        """
        ConversationNotificationService.notify_conversation_updated(
            provedor_id, 
            conversation_id, 
            'conversation_assigned',
            {'assignee_id': assignee_id}
        )
    
    @staticmethod
    def notify_message_received(provedor_id, conversation_id, message_data, conversation_data=None):
        """
        Notifica que uma nova mensagem foi recebida
        
        Args:
            provedor_id: ID do provedor
            conversation_id: ID da conversa
            message_data: Dados da mensagem (id, content, sender, etc)
            conversation_data: Dados da conversa atualizada (opcional, usado quando mensagem é do cliente)
        """
        # Notificar o painel (para atualização da lista de conversas)
        # Incluir conversa atualizada nos dados para que o front possa mover para o topo instantaneamente
        ConversationNotificationService.notify_conversation_updated(
            provedor_id,
            conversation_id,
            'message_received',
            {
                'message': message_data,
                'conversation': conversation_data
            },
            conversation_data=conversation_data,
        )
        
        # Notificar diretamente o grupo da conversa (para atualização em tempo real no ChatArea)
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return
                
            conversation_group = f'conversation_{conversation_id}'
            
            # Sempre incluir conversa se disponível (para atualização instantânea)
            event_data = {
                'type': 'message_received' if conversation_data else 'chat_message',
                'conversation_id': conversation_id, # Campo explícito na raiz
                'message': message_data,
                'conversation': conversation_data,  # Sempre incluir conversa se disponível
                'sender': None,
                'timestamp': datetime.now().isoformat()
            }
            
            # Log para debug (apenas em produção para identificar problemas)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"[ConversationNotification] Notificando RECEBIMENTO: grupo={conversation_group}, "
                f"tipo={event_data['type']}, message_id={message_data.get('id')}"
            )
            
            async_to_sync(channel_layer.group_send)(
                conversation_group,
                event_data
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[ConversationNotification] Erro ao enviar mensagem via WebSocket: {e}", exc_info=True)
    
    @staticmethod
    def notify_message_sent(provedor_id, conversation_id, message_data, conversation_data=None):
        """
        Notifica que uma mensagem foi enviada
        
        Args:
            provedor_id: ID do provedor
            conversation_id: ID da conversa
            message_data: Dados da mensagem
            conversation_data: Dados da conversa atualizada (opcional)
        """
        # Notificar o painel (para atualização da lista de conversas)
        # Incluir conversa atualizada para ordenação instantânea
        ConversationNotificationService.notify_conversation_updated(
            provedor_id,
            conversation_id,
            'message_sent',
            {
                'message': message_data,
                'conversation': conversation_data
            },
            conversation_data=conversation_data,
        )
        
        # Notificar diretamente o grupo da conversa (para atualização em tempo real no ChatArea)
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                return
                
            conversation_group = f'conversation_{conversation_id}'
            
            # Sempre incluir conversa se disponível (para atualização instantânea)
            event_data = {
                'type': 'chat_message',
                'conversation_id': conversation_id, # Campo explícito na raiz
                'message': message_data,
                'conversation': conversation_data,  # Sempre incluir conversa se disponível
                'sender': None,
                'timestamp': datetime.now().isoformat()
            }
            
            # Log para debug (apenas em produção para identificar problemas)
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"[ConversationNotification] Notificando ENVIO: grupo={conversation_group}, "
                f"tipo={event_data['type']}, message_id={message_data.get('id')}"
            )
            
            async_to_sync(channel_layer.group_send)(
                conversation_group,
                event_data
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[ConversationNotification] Erro ao enviar mensagem enviada via WebSocket: {e}", exc_info=True) 