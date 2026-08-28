import json
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.utils import timezone
import asyncio
import logging

logger = logging.getLogger(__name__)

from .models import Conversation

User = get_user_model()


class TokenAuthMixin:
    """
    Mixin simplificado - autenticação já feita pelo middleware TokenAuthMiddleware.
    O middleware lê o token da querystring e preenche scope["user"].
    """

    async def get_authenticated_user(self):
        """
        Retorna o usuário já autenticado pelo middleware.
        O middleware TokenAuthMiddleware já processou o token e preencheu scope["user"].
        """
        user = self.scope.get("user")
        if user and user.is_authenticated:
            return user
        return None


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
            # Timeout reduzido para 100ms para evitar acúmulo em bursts
            await asyncio.wait_for(
                self.send(text_data=text_data),
                timeout=timeout
            )
            return True
        except (asyncio.TimeoutError, Exception):
            return False

    async def _cleanup_group(self, group_name, channel_name):
        """Limpar grupo com timeout curto"""
        try:
            await asyncio.wait_for(
                self.channel_layer.group_discard(group_name, channel_name),
                timeout=0.1
            )
        except (asyncio.TimeoutError, Exception):
            pass


class ConversationConsumer(TokenAuthMixin, SafeConsumerMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer para conversas individuais
    Com autenticação e validação de permissões
    """

    async def connect(self):
        """Conectar ao WebSocket com autenticação"""
        conversation_id = "desconhecida"
        try:
            conversation_id = self.scope.get('url_route', {}).get('kwargs', {}).get('conversation_id', 'desconhecida')
            
            # Verificar se Channel Layer está disponível
            try:
                channel_layer = get_channel_layer()
                if channel_layer is None:
                    await self.close(code=4000)
                    return
            except Exception as e:
                await self.close(code=4000)
                return
            
            # Usar usuário do scope (já autenticado pelo middleware)
            user = self.scope.get("user")
            if user is None or not user.is_authenticated:
                await self.close(code=4001)  # Unauthorized
                return

            self.user = user
            self.conversation_id = conversation_id

            # Validar que o usuário tem acesso à conversa
            has_access = await self.check_conversation_access(self.conversation_id, user)
            if not has_access:
                await self.close(code=4003)  # Forbidden
                return

            self.room_group_name = f"conversation_{self.conversation_id}"

            # Join room group com tratamento de erro
            try:
                await self.channel_layer.group_add(
                    self.room_group_name,
                    self.channel_name,
                )
            except Exception as e:
                await self.close(code=4000)
                return

            await self.accept()

        except KeyError as e:
            try:
                await self.close(code=4000)  # Internal error
            except:
                pass
        except Exception as e:
            try:
                await self.close(code=4000)  # Internal error
            except:
                pass

    @database_sync_to_async
    def check_conversation_access(self, conversation_id, user):
        """
        Verifica se o usuário tem acesso à conversa
        Retorna True se o usuário é superadmin OU pertence ao provedor da conversa
        """
        try:
            # Superadmin pode acessar qualquer conversa
            if hasattr(user, 'user_type') and user.user_type == 'superadmin':
                return True

            conversation = (
                Conversation.objects.select_related("inbox__provedor", "assignee")
                .get(id=conversation_id)
            )

            provedor = conversation.inbox.provedor if conversation.inbox else None
            if not provedor:
                return False

            # Verificar se é admin do provedor
            if hasattr(user, "provedores_admin") and user.provedores_admin.filter(
                id=provedor.id
            ).exists():
                return True

            # Verificar se está atribuído à conversa
            if conversation.assignee and conversation.assignee.id == user.id:
                return True

            # Verificar se é membro do provedor (agente que pode visualizar conversas)
            if hasattr(user, "provedor_id") and user.provedor_id == provedor.id:
                return True
            
            # Verificar se o usuário pertence ao provedor por relação M2M
            if hasattr(user, "provedores") and user.provedores.filter(id=provedor.id).exists():
                return True

            return False

        except Conversation.DoesNotExist:
            return False
        except Exception as e:
            return False


    async def disconnect(self, close_code):
        # Marcar como desconectando para evitar envios
        self._disconnecting = True
        
        # Cancelar todas as tasks em background pendentes
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        
        # Desconectar sem bloquear - fazer limpeza em background
        try:
            if hasattr(self, "room_group_name") and self.room_group_name:
                # Executar group_discard em background sem bloquear
                self._run_background(
                    self._cleanup_group(self.room_group_name, self.channel_name)
                )
        except Exception:
            pass  # Ignorar erros no disconnect

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get("type", "message")

        if message_type == "ping":
            # Respond to ping with pong
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "pong",
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )
            return

        if message_type == "message":
            message = text_data_json["message"]
            sender = text_data_json.get("sender")

            # Send message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": message,
                    "sender": sender,
                    "timestamp": text_data_json.get("timestamp"),
                },
            )
        elif message_type == "typing":
            # Handle typing indicator
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "user": text_data_json.get("user"),
                    "is_typing": text_data_json.get("is_typing", False),
                },
            )

    async def chat_message(self, event):
        """
        Handler para mensagens de chat genéricas.
        Envia uma única mensagem no formato que o frontend espera.
        Frontend verifica: message, chat_message, message_created, message_received
        """
        message = event.get("message")
        sender = event.get("sender")
        timestamp = event.get("timestamp")
        conversation = event.get("conversation")

        # Enviar uma única mensagem com tipo que o frontend reconhece
        # O frontend aceita múltiplos tipos, então usamos o tipo primário
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "chat_message",  # Tipo primário que o frontend verifica
                    "message": message,
                    "sender": sender,
                    "timestamp": timestamp,
                    "conversation": conversation,  # Sempre incluir conversa se disponível
                }
            )
        )

    async def message_received(self, event):
        """
        Handler para mensagens recebidas do cliente com conversa atualizada.
        Inclui a conversa atualizada para atualizar o status da janela de 24 horas.
        Frontend verifica: message_received, message, chat_message, message_created
        """
        message = event.get("message")
        conversation = event.get("conversation")
        timestamp = event.get("timestamp")
        sender = event.get("sender")

        # Enviar uma única mensagem com tipo que o frontend reconhece
        # O frontend aceita múltiplos tipos, então usamos o tipo específico
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "message_received",  # Tipo específico que o frontend verifica
                    "message": message,
                    "conversation": conversation,  # Sempre incluir conversa atualizada
                    "sender": sender,
                    "timestamp": timestamp,
                }
            )
        )
        
        # Log para debug em produção (apenas se message_id disponível)
        message_id = message.get('id') if message else None
        if message_id:
            logger.debug(
                f"[ConversationConsumer] Mensagem {message_id} enviada via WebSocket "
                f"para conversa {self.conversation_id}, tipo: message_received"
            )

    async def typing_indicator(self, event):
        """
        Handler para indicadores de digitação (typing indicators)
        Recebe eventos tanto do frontend quanto do webhook do WhatsApp
        """
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "typing",
                    "conversation_id": event.get("conversation_id"),
                    "is_typing": event.get("is_typing", False),
                    "from_number": event.get("from_number"),
                    "timestamp": event.get("timestamp"),
                }
            )
        )

    async def message_status_update(self, event):
        """
        Handler para atualizações de status de mensagens (sent, delivered, read)
        """
        await self._safe_send(text_data=json.dumps({
            'type': 'message_status_update',
            'message_id': event.get('message_id'),
            'status': event.get('status'),
            'timestamp': event.get('timestamp')
        }))

    async def message_updated(self, event):
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "message_updated",
                    "action": event.get("action"),
                    "message": event.get("message"),
                    "sender": event.get("sender"),
                    "timestamp": event.get("timestamp", timezone.now().isoformat()),
                }
            )
        )

    async def message_reaction(self, event):
        """
        Handler para reações de mensagens
        """
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "message_reaction",
                    "message_id": event.get("message_id"),
                    "reaction": event.get("reaction"),
                }
            )
        )


class NotificationConsumer(TokenAuthMixin, SafeConsumerMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer para notificações de usuário
    Com autenticação e validação de permissões
    """

    async def connect(self):
        """Conectar ao WebSocket com autenticação"""
        try:
            # Usar usuário do scope (já autenticado pelo middleware)
            user = self.scope.get("user")
            if user is None or not user.is_authenticated:
                await self.close(code=4001)  # Unauthorized
                return

            self.user = user
            requested_user_id = self.scope["url_route"]["kwargs"]["user_id"]

            # Validar que o usuário só pode acessar suas próprias notificações
            if str(user.id) != str(requested_user_id):
                await self.close(code=4003)  # Forbidden
                return

            self.user_id = user.id
            self.room_group_name = f"notifications_{self.user_id}"

            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name,
            )

            await self.accept()

        except Exception as e:
            await self.close(code=4000)  # Internal error

    async def disconnect(self, close_code):
        # Marcar como desconectando para evitar envios
        self._disconnecting = True
        
        # Cancelar todas as tasks em background pendentes
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        
        # Desconectar sem bloquear - fazer limpeza em background
        try:
            if hasattr(self, "room_group_name") and self.room_group_name:
                # Executar group_discard em background sem bloquear
                self._run_background(
                    self._cleanup_group(self.room_group_name, self.channel_name)
                )
        except Exception:
            pass  # Ignorar erros no disconnect

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        # notification_type = text_data_json.get('type', 'notification')  # reservado se precisar

        # Send notification to room group
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "send_notification",
                "notification": text_data_json,
            },
        )

    async def send_notification(self, event):
        notification = event["notification"]
        await self._safe_send(text_data=json.dumps(notification))


class DashboardConsumer(TokenAuthMixin, SafeConsumerMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer para dashboard de conversas
    Com autenticação
    """

    async def connect(self):
        """Conectar ao WebSocket com autenticação"""
        try:
            # Usar usuário do scope (já autenticado pelo middleware)
            user = self.scope.get("user")
            if user is None or not user.is_authenticated:
                await self.close(code=4001)  # Unauthorized
                return

            self.user = user
            
            # Tentar obter o provedor_id do usuário
            self.provedor_id = await self.get_user_provedor_id(user)
            
            # Grupos
            self.groups = ["conversas_dashboard"] # Grupo global legado
            if self.provedor_id:
                # Grupo específico do provedor para estatísticas e eventos filtrados
                self.groups.append(f"dashboard_{self.provedor_id}")
            
            # Adicionar a todos os grupos
            for group_name in self.groups:
                await self.channel_layer.group_add(
                    group_name,
                    self.channel_name,
                )

            await self.accept()

        except Exception as e:
            logger.error(f"[DashboardConsumer] Erro ao conectar: {e}")
            await self.close(code=4000)  # Internal error

    @database_sync_to_async
    def get_user_provedor_id(self, user):
        """Obtém o ID do provedor do usuário logado"""
        try:
            # 1. Através do campo provedor_id (comum para agentes/admins)
            if hasattr(user, 'provedor_id') and user.provedor_id:
                return user.provedor_id
            
            # 2. Através de relacionamento M2M ou Admin
            from core.models import Provedor
            prov = Provedor.objects.filter(admins=user).first()
            if prov:
                return prov.id
            
            # 3. Superadmin pode não ter provedor fixo (usar da querystring se necessário, 
            # mas aqui o dashboard é sempre de um provedor)
            return None
        except Exception:
            return None

    async def disconnect(self, close_code):
        # Marcar como desconectando para evitar envios
        self._disconnecting = True
        
        # Cancelar todas as tasks em background pendentes
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        
        # Desconectar sem bloquear - fazer limpeza em background
        try:
            if hasattr(self, "groups"):
                for group_name in self.groups:
                    self._run_background(
                        self._cleanup_group(group_name, self.channel_name)
                    )
        except Exception:
            pass  # Ignorar erros no disconnect

    async def dashboard_event(self, event):
        await self._safe_send(text_data=json.dumps(event["data"]))

    async def dashboard_stats_update(self, event):
        """Notifica o frontend para recarregar as contagens do dashboard"""
        await self._safe_send(text_data=json.dumps({
            "type": "dashboard_stats_update",
            "timestamp": timezone.now().isoformat()
        }))


class PainelConsumer(TokenAuthMixin, SafeConsumerMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer para painel do provedor
    Com autenticação e validação de permissões
    """

    async def connect(self):
        """Conectar ao WebSocket com autenticação"""
        try:
            # Usar usuário do scope (já autenticado pelo middleware)
            user = self.scope.get("user")
            if user is None or not user.is_authenticated:
                await self.close(code=4001)  # Unauthorized
                return

            self.user = user
            requested_provedor_id = self.scope["url_route"]["kwargs"]["provedor_id"]

            # Validar que o usuário tem acesso ao provedor
            has_access = await self.check_provedor_access(requested_provedor_id, user)
            if not has_access:
                await self.close(code=4003)  # Forbidden
                return

            self.provedor_id = requested_provedor_id
            self.room_group_name = f"painel_{self.provedor_id}"

            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name,
            )

            await self.accept()

        except Exception as e:
            await self.close(code=4000)  # Internal error

    @database_sync_to_async
    def check_provedor_access(self, provedor_id, user):
        """
        Verifica se o usuário tem acesso ao provedor
        Retorna True se o usuário é superadmin OU é admin do provedor
        """
        try:
            from core.models import Provedor

            # Superadmin pode acessar qualquer provedor
            if hasattr(user, 'user_type') and user.user_type == 'superadmin':
                return True

            provedor = Provedor.objects.get(id=provedor_id)

            if hasattr(user, "provedores_admin") and user.provedores_admin.filter(
                id=provedor.id
            ).exists():
                return True

            return False

        except Exception as e:
            return False

    async def disconnect(self, close_code):
        # Marcar como desconectando para evitar envios
        self._disconnecting = True
        
        # Cancelar todas as tasks em background pendentes
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        
        # Desconectar sem bloquear - fazer limpeza em background
        try:
            if hasattr(self, "room_group_name") and self.room_group_name:
                # Executar group_discard em background sem bloquear
                self._run_background(
                    self._cleanup_group(self.room_group_name, self.channel_name)
                )
        except Exception:
            pass  # Ignorar erros no disconnect

    async def uazapi_event(self, event):
        await self._safe_send(text_data=json.dumps(event["event"]))

    async def dashboard_event(self, event):
        await self._safe_send(text_data=json.dumps(event["data"]))

    async def system_message(self, event):
        """Handler para mensagens do sistema"""
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "system_message",
                    "message": event.get("message", {}),
                    "timestamp": event.get("timestamp", "")
                }
            )
        )

    async def conversation_event(self, event):
        """Handler para eventos de conversa"""
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "conversation_event",
                    "event_type": event["event_type"],
                    "conversation_id": event["conversation_id"],
                    "data": event["data"],
                    "timestamp": event["timestamp"],
                }
            )
        )

    async def conversation_status_changed(self, event):
        """Handler para mudanças de status de conversa"""
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "conversation_status_changed",
                    "conversation": event["conversation"],
                    "message": event["message"],
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )


class UserStatusConsumer(TokenAuthMixin, SafeConsumerMixin, AsyncWebsocketConsumer):
    async def connect(self):
        # Usar usuário do scope (já autenticado pelo middleware)
        user = self.scope.get("user")
        
        # Verificação robusta de autenticação
        if not user or not hasattr(user, 'is_authenticated') or not user.is_authenticated:
            logger.warning("UserStatusConsumer: Conexão rejeitada - usuário não autenticado")
            await self.close(code=4001)
            return
        
        # Verificar se é usuário válido (não AnonymousUser)
        if not hasattr(user, 'id') or user.id is None:
            logger.warning("UserStatusConsumer: Conexão rejeitada - AnonymousUser")
            await self.close(code=4001)
            return

        self.user_id = user.id
        self.room_group_name = "user_status_global"
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        await self.accept()

        # Marcar usuário como online
        await self.set_user_online(True)

    async def disconnect(self, close_code):
        # Marcar como desconectando para evitar envios
        self._disconnecting = True
        
        # Cancelar todas as tasks em background pendentes
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        
        # Desconectar sem bloquear - fazer limpeza em background
        try:
            import asyncio
            # Executar todas as operações de limpeza em background sem bloquear
            if hasattr(self, "user_id") and self.user_id:
                # Atualizar status em background (não bloquear)
                self._run_background(
                    self._set_user_online_async(False)
                )
            
            # Sair do grupo em background
            if hasattr(self, "room_group_name") and self.room_group_name:
                self._run_background(
                    self._cleanup_group(self.room_group_name, self.channel_name)
                )
        except Exception:
            pass  # Ignorar erros no disconnect
    
    async def _set_user_online_async(self, online):
        """Atualizar status online em background com timeout adequado"""
        try:
            import asyncio
            await asyncio.wait_for(
                self.set_user_online(online),
                timeout=5.0  # Aumentado para 5s para acomodar latência de rede externa
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.error(f"UserStatusConsumer: Erro ao atualizar status online: {str(e)}")
            pass  # Ignorar timeout/erros para não quebrar o disconnect

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get("type") == "ping":
            if hasattr(self, "user_id") and self.user_id:
                await self.refresh_last_seen()
                await self._safe_send(text_data=json.dumps({"type": "pong"}))

    async def user_status_update(self, event):
        await self._safe_send(
            text_data=json.dumps(
                {
                    "type": "user_status_update",
                    "user_id": event["user_id"],
                    "is_online": event["is_online"],
                    "last_seen": event["last_seen"],
                }
            )
        )

    @database_sync_to_async
    def _update_user_db_status(self, is_online):
        """Atualiza apenas o banco de dados de forma síncrona"""
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(id=self.user_id)
            user.is_online = is_online
            user.last_seen = timezone.now()
            user.save(update_fields=["is_online", "last_seen"])
            return user.id, user.last_seen
        except UserModel.DoesNotExist:
            return None, None

    async def set_user_online(self, is_online):
        """Método assíncrono para atualizar banco e notificar via Redis"""
        if not hasattr(self, "user_id") or not self.user_id:
            return

        # 1. Atualizar banco de dados de forma segura (thread separate)
        user_id, last_seen = await self._update_user_db_status(is_online)
        
        if not user_id:
            return

        # 2. Notificar outros usuários via Channel Layer (Redis) de forma assíncrona
        try:
            await self.channel_layer.group_send(
                "user_status_global",
                {
                    "type": "user_status_update",
                    "user_id": user_id,
                    "is_online": is_online,
                    "last_seen": last_seen.isoformat() if last_seen else None,
                },
            )
        except Exception as e:
            logger.error(f"UserStatusConsumer: Erro ao enviar notificação de status para o Redis: {str(e)}")

    @database_sync_to_async
    def refresh_last_seen(self):
        if not hasattr(self, "user_id") or not self.user_id:
            return

        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(id=self.user_id)
            user.last_seen = timezone.now()
            user.save(update_fields=["last_seen"])
        except UserModel.DoesNotExist:
            pass