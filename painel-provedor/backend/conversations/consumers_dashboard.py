import json
import logging
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)

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


class DashboardConsumer(SafeConsumerMixin, AsyncWebsocketConsumer):
    """
    WebSocket consumer para atualizações em tempo real do dashboard
    """
    
    async def connect(self):
        """Conectar ao WebSocket"""
        try:
            # Autenticar usuário
            user = await self.get_user()
            if not user:
                await self.close()
                return
            
            # Obter provedor do usuário
            provedor = await self.get_user_provedor(user)
            if not provedor:
                await self.close()
                return
            
            # Adicionar ao grupo do provedor
            self.provedor_id = provedor.id
            self.user = user
            
            await self.channel_layer.group_add(
                f"dashboard_{provedor.id}",
                self.channel_name
            )
            
            await self.accept()
            
            # Enviar dados iniciais
            await self.send_initial_data()
            
            
        except Exception as e:
            logger.error(f"Erro ao conectar WebSocket do dashboard: {e}")
            await self.close()
    
    async def disconnect(self, close_code):
        """Desconectar do WebSocket - não bloqueante"""
        # Marcar como desconectando para evitar envios
        self._disconnecting = True
        
        # Cancelar todas as tasks em background pendentes
        for task in list(self._background_tasks):
            if not task.done():
                task.cancel()
        
        # Não bloquear o disconnect - fazer limpeza em background se necessário
        try:
            if hasattr(self, 'provedor_id'):
                # Executar group_discard em background sem bloquear
                self._run_background(
                    self._cleanup_group(f"dashboard_{self.provedor_id}", self.channel_name)
                )
        except Exception:
            pass  # Ignorar erros no disconnect

    async def receive(self, text_data):
        """Receber mensagem do cliente"""
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'request_update':
                # Cliente solicitou atualização
                await self.send_dashboard_update()
            elif message_type == 'ping':
                # Ping do cliente
                await self._safe_send(text_data=json.dumps({'type': 'pong'}))
                
        except json.JSONDecodeError:
            logger.error("Erro ao decodificar JSON do WebSocket")
        except Exception as e:
            logger.error(f"Erro ao processar mensagem WebSocket: {e}")
    
    async def send_initial_data(self):
        """Enviar dados iniciais do dashboard"""
        try:
            dashboard_data = await self.get_dashboard_data()
            await self._safe_send(text_data=json.dumps({
                'type': 'dashboard_update', # Frontend espera dashboard_update
                'stats': dashboard_data
            }))
        except Exception as e:
            logger.error(f"Erro ao enviar dados iniciais: {e}")
    
    async def send_dashboard_update(self):
        """Enviar atualização do dashboard"""
        try:
            dashboard_data = await self.get_dashboard_data()
            await self._safe_send(text_data=json.dumps({
                'type': 'dashboard_update',
                'stats': dashboard_data
            }))
        except Exception as e:
            logger.error(f"Erro ao enviar atualização: {e}")
    
    async def dashboard_stats_update(self, event):
        """Enviar atualização de estatísticas para o cliente"""
        try:
            dashboard_data = await self.get_dashboard_data()
            await self._safe_send(text_data=json.dumps({
                'type': 'dashboard_update', # Frontend espera dashboard_update
                'stats': dashboard_data
            }))
        except Exception as e:
            logger.error(f"Erro ao enviar atualização de estatísticas: {e}")
    
    @database_sync_to_async
    def get_user(self):
        """Obter usuário autenticado"""
        try:
            # Verificar se há token na query string
            query_string = self.scope.get('query_string', b'').decode()
            if 'token=' in query_string:
                from rest_framework.authtoken.models import Token
                token_key = query_string.split('token=')[1].split('&')[0]
                token = Token.objects.select_related('user').get(key=token_key)
                return token.user
            return None
        except Exception as e:
            logger.error(f"Erro ao obter usuário: {e}")
            return None
    
    @database_sync_to_async
    def get_user_provedor(self, user):
        """Obter provedor do usuário"""
        try:
            if hasattr(user, 'provedor') and user.provedor:
                return user.provedor
            return user.provedores_admin.first()
        except Exception as e:
            logger.error(f"Erro ao obter provedor: {e}")
            return None
    
    @database_sync_to_async
    def get_dashboard_data(self):
        """Obter dados do dashboard usando a lógica oficial sincronizada"""
        try:
            from django.contrib.auth import get_user_model
            from django.db.models import Q, Count
            from conversations.models import Conversation, Message
            from conversations.views import ConversationViewSet
            from rest_framework.test import APIRequestFactory
            
            provedor_id = self.provedor_id
            user = self.user
            
            # Simular request para usar get_queryset do ConversationViewSet
            factory = APIRequestFactory()
            request = factory.get('/')
            request.user = user
            
            viewset = ConversationViewSet()
            viewset.request = request
            viewset.action = 'list'
            
            # Queryset oficial (respeita equipes e permissões)
            qs_ativas = viewset.get_queryset()
            
            # Estatísticas sincronizadas com DashboardStatsView
            stats = qs_ativas.aggregate(
                atendimento=Count('id', filter=Q(assignee__isnull=False)),
                ia=Count('id', filter=Q(assignee__isnull=True, status='snoozed')),
                espera=Count('id', filter=Q(assignee__isnull=True) & (Q(status='pending') | Q(additional_attributes__has_key='assigned_team')))
            )
            
            # Totais históricos
            total_stats = Conversation.objects.filter(inbox__provedor_id=provedor_id).aggregate(
                total=Count('id'),
                finalizadas=Count('id', filter=Q(status__in=['closed', 'encerrada', 'resolved', 'finalizada']))
            )
            
            conversas_abertas = stats['atendimento'] or 0
            conversas_pendentes = stats['espera'] or 0
            conversas_ia = stats['ia'] or 0
            
            return {
                'conversas_abertas': conversas_abertas,
                'conversas_pendentes': conversas_pendentes,
                'na_automacao': conversas_ia,
                'conversas_resolvidas': total_stats['finalizadas'] or 0,
                'total_conversas': total_stats['total'] or 0,
                'conversas_em_andamento': conversas_abertas + conversas_pendentes + conversas_ia,
                'timestamp': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter dados do dashboard: {e}")
            return {}
    
    @classmethod
    async def broadcast_dashboard_update(cls, provedor_id):
        """Broadcast atualização para todos os clientes do provedor"""
        try:
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            
            await channel_layer.group_send(
                f"dashboard_{provedor_id}",
                {
                    'type': 'dashboard_stats_update'
                }
            )
        except Exception as e:
            logger.error(f"Erro ao broadcast dashboard: {e}") 