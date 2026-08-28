import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone

class SafeConsumerMixin:
    """
    Mixin para fornecer métodos de envio seguro e limpeza não-bloqueante
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._disconnecting = False
        self._background_tasks = set()

    def _run_background(self, coro):
        """Executa uma corotina em background e mantém rastreamento"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def _safe_send(self, text_data, timeout=0.1):
        """Enviar mensagem de forma segura com timeout e verificação de conexão"""
        if getattr(self, '_disconnecting', False):
            return False
        try:
            await asyncio.wait_for(
                self.send(text_data=text_data),
                timeout=timeout
            )
            return True
        except (asyncio.TimeoutError, Exception):
            return False

    async def _cleanup_group(self, group_name, channel_name):
        """Limpar grupo em background com timeout curto"""
        try:
            await asyncio.wait_for(
                self.channel_layer.group_discard(group_name, channel_name),
                timeout=0.1
            )
        except (asyncio.TimeoutError, Exception):
            pass

User = get_user_model()


class PrivateChatConsumer(SafeConsumerMixin, AsyncWebsocketConsumer):
    """
    Consumer WebSocket para chat privado entre usuários
    """
    
    async def connect(self):
        """
        Conectar ao WebSocket de chat privado
        """
        self.user = self.scope.get('user')
        
        # Verificação robusta de autenticação
        if not self.user or not hasattr(self.user, 'is_authenticated') or not self.user.is_authenticated:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PrivateChatConsumer: Conexão rejeitada - usuário não autenticado")
            await self.close(code=4001)
            return
        
        # Verificar se é usuário válido (não AnonymousUser)
        if not hasattr(self.user, 'id') or self.user.id is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("PrivateChatConsumer: Conexão rejeitada - AnonymousUser")
            await self.close(code=4001)
            return
        
        # Criar grupo único para este usuário
        self.room_group_name = f'private_chat_{self.user.id}'
        
        # Entrar no grupo
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        
        await self.accept()
        
        # Enviar confirmação de conexão
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'user_id': self.user.id,
            'username': self.user.username,
            'message': 'Conectado ao chat privado'
        }))
        
    
    async def disconnect(self, close_code):
        """
        Desconectar do WebSocket - não bloqueante
        """
        # Marcar como desconectando para evitar envios
        self._disconnecting = True
        
        # Cancelar todas as tasks em background pendentes
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        
        try:
            if hasattr(self, 'room_group_name'):
                # Executar group_discard em background sem bloquear
                self._run_background(
                    self._cleanup_group(self.room_group_name, self.channel_name)
                )
        except Exception:
            pass  # Ignorar erros no disconnect

    async def receive(self, text_data):
        """
        Receber mensagens do WebSocket
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'ping':
                # Responder ping com pong
                await self.send(text_data=json.dumps({
                    'type': 'pong',
                    'timestamp': timezone.now().isoformat()
                }))
            elif message_type == 'typing':
                # Indicador de digitação
                await self.handle_typing(data)
            elif message_type == 'message':
                # Enviar mensagem privada
                await self.handle_private_message(data)
            elif message_type == 'join_notifications':
                # Mensagem de join do frontend - apenas confirmar conexão
                await self.send(text_data=json.dumps({
                    'type': 'notifications_joined',
                    'user_id': self.user.id
                }))
                
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Formato de mensagem inválido'
            }))
        except Exception as e:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Erro ao processar mensagem'
            }))
    
    async def handle_typing(self, data):
        """
        Lidar com indicador de digitação
        """
        target_user_id = data.get('target_user_id')
        is_typing = data.get('is_typing', False)
        
        if target_user_id:
            # Enviar para o grupo do usuário de destino
            target_group_name = f'private_chat_{target_user_id}'
            await self.channel_layer.group_send(
                target_group_name,
                {
                    'type': 'typing_indicator',
                    'from_user_id': self.user.id,
                    'from_username': self.user.username,
                    'is_typing': is_typing
                }
            )
    
    async def handle_private_message(self, data):
        """
        Lidar com mensagem privada
        """
        target_user_id = data.get('target_user_id')
        message_content = data.get('message')
        
        if not target_user_id or not message_content:
            await self._safe_send(text_data=json.dumps({
                'type': 'error',
                'message': 'target_user_id e message são obrigatórios'
            }))
            return
        
        # Enviar mensagem para o grupo do usuário de destino
        target_group_name = f'private_chat_{target_user_id}'
        await self.channel_layer.group_send(
            target_group_name,
            {
                'type': 'private_message',
                'from_user_id': self.user.id,
                'from_username': self.user.username,
                'message': message_content,
                'timestamp': timezone.now().isoformat()
            }
        )
    
    async def typing_indicator(self, event):
        """
        Enviar indicador de digitação para o WebSocket
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'typing',
            'from_user_id': event['from_user_id'],
            'from_username': event['from_username'],
            'is_typing': event['is_typing']
        }))
    
    async def private_message(self, event):
        """
        Enviar mensagem privada para o WebSocket
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'private_message',
            'from_user_id': event['from_user_id'],
            'from_username': event['from_username'],
            'message': event['message'],
            'timestamp': event['timestamp']
        }))
    
    async def message_sent(self, event):
        """
        Handler para quando uma mensagem é enviada via API
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'message_sent',
            'message': event.get('message'),
            'timestamp': event.get('timestamp')
        }))
    
    async def message_received(self, event):
        """
        Handler para quando uma mensagem é recebida
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'message_received',
            'message': event.get('message'),
            'from_user_id': event.get('from_user_id'),
            'timestamp': event.get('timestamp')
        }))
    
    async def new_private_message(self, event):
        """
        Handler para nova mensagem privada recebida via WebSocket
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'new_private_message',
            'message': event.get('message')
        }))
    
    async def message_read(self, event):
        """
        Handler para quando uma mensagem foi lida
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'message_read',
            'message_id': event.get('message_id'),
            'reader_id': event.get('reader_id')
        }))
    
    async def unread_count_update(self, event):
        """
        Handler para atualizar contador de mensagens não lidas
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'unread_count_update',
            'unread_counts': event.get('unread_counts', {})
        }))




