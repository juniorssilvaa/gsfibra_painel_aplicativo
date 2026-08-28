from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.views import APIView
from rest_framework.authentication import TokenAuthentication
from django.shortcuts import get_object_or_404
from django.db.models import Q, Count, Max
from django.contrib.auth import get_user_model
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.core.files.storage import default_storage
from django.conf import settings
from django.http import FileResponse, Http404
from django.views.decorators.http import require_http_methods
import uuid
import os
import mimetypes
import logging

from .models import PrivateMessage, PrivateMessageReaction, CSATFeedback
from core.models import Provedor

User = get_user_model()
logger = logging.getLogger(__name__)


@require_http_methods(['GET', 'HEAD'])
def serve_private_chat_media(request, filename):
    """
    Serve arquivos de mídia do chat interno (/media/private_chat/<filename>).
    Requer URL assinada ou Authorization: Token com ACL (sender/recipient).
    """
    from urllib.parse import unquote
    from django.http import HttpResponseForbidden
    from core.media_signing import (
        media_require_signed_url,
        user_may_access_private_chat_file,
        verify_request_media_signature,
    )
    from core.auth_token_cache import user_from_token_key

    safe_name = unquote(filename or '').strip()
    if not safe_name or '..' in safe_name or '/' in safe_name or '\\' in safe_name:
        raise Http404('Arquivo inválido')

    signed_ok = verify_request_media_signature(request)
    auth_user = None
    auth_header = request.META.get('HTTP_AUTHORIZATION') or ''
    if auth_header.startswith('Token '):
        auth_user = user_from_token_key(auth_header[7:].strip())

    if media_require_signed_url():
        if not signed_ok:
            if not auth_user or not user_may_access_private_chat_file(auth_user, safe_name):
                return HttpResponseForbidden('Assinatura de mídia inválida ou expirada')
        elif auth_user and not user_may_access_private_chat_file(auth_user, safe_name):
            return HttpResponseForbidden('Sem permissão para esta mídia')

    file_path = os.path.join(settings.MEDIA_ROOT, 'private_chat', safe_name)
    if not os.path.isfile(file_path):
        logger.warning('[PrivateChatMedia] Arquivo não encontrado: %s', file_path)
        raise Http404('Arquivo não encontrado')

    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        lower = safe_name.lower()
        if lower.endswith('.webm'):
            content_type = 'audio/webm'
        elif lower.endswith(('.ogg', '.oga')):
            content_type = 'audio/ogg'
        elif lower.endswith('.mp3'):
            content_type = 'audio/mpeg'
        elif lower.endswith('.wav'):
            content_type = 'audio/wav'
        else:
            content_type = 'application/octet-stream'

    response = FileResponse(open(file_path, 'rb'), content_type=content_type)
    response['Cache-Control'] = 'private, max-age=60'
    response['Access-Control-Allow-Origin'] = request.headers.get('Origin', '') or '*'
    response['Access-Control-Allow-Methods'] = 'GET, HEAD, OPTIONS'
    response['Vary'] = 'Origin'
    response['Accept-Ranges'] = 'bytes'
    if request.method == 'HEAD':
        response.close()
    return response


class PrivateMessageViewSet(viewsets.ModelViewSet):
    """
    ViewSet para mensagens privadas
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get_queryset(self):
        user = self.request.user
        other_user_id = self.request.query_params.get('other_user_id') or self.request.query_params.get('user_id')
        
        if not other_user_id:
            return PrivateMessage.objects.none()
        
        # Buscar provedor do usuário
        provedor = self._get_user_provedor(user)
        
        if not provedor:
            return PrivateMessage.objects.none()
        
        # Retornar mensagens entre os dois usuários do mesmo provedor
        # Verificar se ambos são do mesmo provedor antes de retornar mensagens
        try:
            other_user = User.objects.get(id=other_user_id)
            other_user_provedor = self._get_user_provedor(other_user)
            
            if provedor != other_user_provedor:
                return PrivateMessage.objects.none()
            
            messages = PrivateMessage.objects.filter(
            is_deleted=False
        ).filter(
            Q(sender=user, recipient_id=other_user_id) |
            Q(sender_id=other_user_id, recipient=user)
        ).select_related('sender', 'recipient', 'reply_to', 'reply_to__sender').prefetch_related('reactions__user').order_by('created_at')
            
            return messages
            
        except User.DoesNotExist:
            return PrivateMessage.objects.none()
    
    def get_serializer_class(self):
        from .serializers_private_chat import PrivateMessageSerializer, PrivateMessageCreateSerializer
        if self.action == 'create':
            return PrivateMessageCreateSerializer
        return PrivateMessageSerializer
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        from .serializers_private_chat import PrivateMessageSerializer
        output = PrivateMessageSerializer(serializer.instance, context={'request': request})
        headers = self.get_success_headers(output.data)
        return Response(output.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        user = self.request.user
        recipient_id = self.request.data.get('recipient_id')
        
        # Verificar se o destinatário existe e é do mesmo provedor
        try:
            recipient = User.objects.get(id=recipient_id)
        except User.DoesNotExist:
            raise permissions.PermissionDenied("Destinatário não encontrado")
        
        provedor = self._get_user_provedor(user)
        recipient_provedor = self._get_user_provedor(recipient)
        
        if not provedor or provedor != recipient_provedor:
            raise permissions.PermissionDenied("Você só pode conversar com usuários do mesmo provedor")
        
        # Processar upload de arquivo se houver
        file_data = self._handle_file_upload(self.request)
        
        message = serializer.save(
            sender=user,
            recipient=recipient,
            provedor=provedor,  # Adicionar o campo provedor obrigatório
            **file_data
        )
        
        # Marcar como lida pelo remetente
        message.mark_as_read()
        
        # Notificar via WebSocket
        self._notify_new_message(message)
        
        # O ViewSet já cria a resposta automaticamente baseada no serializer
    
    def _get_user_provedor(self, user):
        """Buscar provedor do usuário"""
        # Primeiro tentar pelo atributo provedor
        if hasattr(user, 'provedor') and user.provedor:
            return user.provedor
        
        # Depois tentar pelos provedores admin
        admin_provedor = user.provedores_admin.first()
        return admin_provedor
    
    def _handle_file_upload(self, request):
        """Processar upload de arquivo"""
        file_data = {}
        uploaded_file = request.FILES.get('file')
        
        if uploaded_file:
            # Gerar nome único
            file_extension = os.path.splitext(uploaded_file.name)[1].lower()
            unique_filename = f"private_chat/{uuid.uuid4()}{file_extension}"
            
            # Salvar arquivo
            file_path = default_storage.save(unique_filename, uploaded_file)
            file_url = default_storage.url(file_path)
            if file_url and not file_url.startswith('/'):
                file_url = f"/{file_url.lstrip('/')}"
            
            content_type = (uploaded_file.content_type or '').lower()
            requested_type = (request.data.get('message_type') or '').strip().lower()
            audio_exts = {'.webm', '.ogg', '.oga', '.mp3', '.wav', '.m4a', '.opus', '.aac'}
            image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
            # .webm pode ser áudio (gravação do mic) — não tratar como vídeo só pela extensão
            video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.m4v'}
            name_lower = (uploaded_file.name or '').lower()

            if requested_type == 'audio':
                message_type = 'audio'
            elif content_type.startswith('image/') or file_extension in image_exts:
                message_type = 'image'
            elif content_type.startswith('audio/') or file_extension in audio_exts:
                message_type = 'audio'
            elif 'audio-message' in name_lower and file_extension in {'.webm', '.ogg'}:
                message_type = 'audio'
            elif content_type.startswith('video/') or file_extension in video_exts:
                message_type = 'video'
            elif file_extension == '.webm' and content_type.startswith('video/'):
                message_type = 'video'
            elif file_extension == '.webm':
                message_type = 'audio'
            else:
                message_type = 'file'
            
            file_data = {
                'file_url': file_url,
                'file_name': uploaded_file.name,
                'file_size': uploaded_file.size,
                'message_type': message_type
            }
        
        return file_data
    
    def _notify_new_message(self, message):
        """Notificar nova mensagem via WebSocket e atualizar contador"""
        channel_layer = get_channel_layer()
        
        # Serializar mensagem para envio
        from .serializers_private_chat import PrivateMessageSerializer
        message_data = PrivateMessageSerializer(message).data
        
        # Notificar o destinatário com a nova mensagem
        recipient_group_name = f"private_chat_{message.recipient.id}"
        
        try:
            # Enviar nova mensagem para o destinatário
            async_to_sync(channel_layer.group_send)(
                recipient_group_name,
                {
                    'type': 'new_private_message',
                    'message': message_data
                }
            )
            
            # Calcular contadores atualizados de mensagens não lidas para o destinatário
            unread_counts = PrivateMessage.objects.filter(
                recipient=message.recipient,
                is_read=False,
                is_deleted=False
            ).values('sender').annotate(
                count=Count('id')
            )
            
            # Converter para dict {sender_id: count}
            unread_counts_dict = {item['sender']: item['count'] for item in unread_counts}
            
            # Enviar atualização do contador para o destinatário
            async_to_sync(channel_layer.group_send)(
                recipient_group_name,
                {
                    'type': 'unread_count_update',
                    'unread_counts': unread_counts_dict
                }
            )
            
        except Exception:
            pass
    
    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        """Marcar mensagem como lida"""
        message = self.get_object()
        user = request.user
        
        # Só o destinatário pode marcar como lida
        if message.recipient == user:
            message.mark_as_read()
            
            # Notificar o remetente via WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"private_chat_{message.sender.id}",
                {
                    'type': 'message_read',
                    'message_id': message.id,
                    'reader_id': user.id
                }
            )
        
        return Response({'message': 'Mensagem marcada como lida'})
    
    @action(detail=True, methods=['post'])
    def react(self, request, pk=None):
        """Reagir a uma mensagem"""
        message = self.get_object()
        user = request.user
        emoji = request.data.get('emoji')
        
        if not emoji:
            return Response({'error': 'Emoji é obrigatório'}, status=400)
        
        # Criar ou remover reação
        reaction, created = PrivateMessageReaction.objects.get_or_create(
            message=message,
            user=user,
            emoji=emoji
        )
        
        if not created:
            reaction.delete()
            action_type = 'reaction_removed'
        else:
            action_type = 'reaction_added'
        
        # Notificar via WebSocket
        channel_layer = get_channel_layer()
        other_user = message.sender if message.recipient == user else message.recipient
        
        async_to_sync(channel_layer.group_send)(
            f"private_chat_{other_user.id}",
            {
                'type': action_type,
                'message_id': message.id,
                'user_id': user.id,
                'emoji': emoji
            }
        )
        
        return Response({'message': f'Reação {emoji} {"adicionada" if created else "removida"}'})

class PrivateUnreadCountsView(APIView):
    """
    API para buscar contadores de mensagens não lidas por usuário
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        try:
            provedor = self._get_user_provedor(user)
        
            if provedor:
                # Buscar contadores de mensagens não lidas por usuário
                unread_counts = PrivateMessage.objects.filter(
                    provedor=provedor,
                    recipient=user,
                    is_read=False,
                    is_deleted=False
                ).values('sender').annotate(
                    count=Count('id')
                ).order_by('-count')
                
                # Converter para dict {user_id: count}
                result = {item['sender']: item['count'] for item in unread_counts}
            
            else:
                # Se não tiver provedor, retornar contadores vazios
                result = {}
            
            return Response(result)
            
        except Exception as e:
            # Retornar contadores vazios em caso de erro
            return Response({})
    
    def _get_user_provedor(self, user):
        """Buscar provedor do usuário"""
        if hasattr(user, 'provedor') and user.provedor:
            return user.provedor
        return user.provedores_admin.first()

class UsersListView(APIView):
    """
    API para listar usuários do mesmo provedor
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        
        try:
            # Tentar buscar provedor do usuário
            provedor = self._get_user_provedor(user)
            
            if provedor:
                # Buscar usuários do mesmo provedor (exceto o atual)
                # Incluir tanto admins quanto agents do provedor
                users = User.objects.filter(
                    Q(provedores_admin=provedor) | Q(provedor=provedor)
                ).exclude(id=user.id).distinct()
            else:
                # Se não tiver provedor, buscar todos os usuários ativos (exceto o atual)
                users = User.objects.filter(is_active=True).exclude(id=user.id)

            # Ocultar niohub/superadmin (lista de usuários / chat privado)
            from core.support_account import exclude_hidden_provedor_users
            users = exclude_hidden_provedor_users(users, viewer=user)
            
            # Serializar dados básicos (simplificado para evitar problemas de serialização)
            users_data = []
            for u in users:
                user_data = {
                    'id': u.id,
                    'username': u.username,
                    'first_name': u.first_name or '',
                    'last_name': u.last_name or '',
                    'avatar': None,  # Simplificado - sem avatar por enquanto
                    'user_type': u.user_type or 'agent',
                    'is_online': bool(u.is_online),
                    'email': u.email or '',
                    'provedor_nome': provedor.nome if provedor else ''
                }
                users_data.append(user_data)
            
            return Response(users_data)
        
        except Exception as e:
            # Retornar lista vazia em caso de erro
            return Response([])
    
    def _get_user_provedor(self, user):
        """Buscar provedor do usuário"""
        if hasattr(user, 'provedor') and user.provedor:
            return user.provedor
        return user.provedores_admin.first()

class DashboardStatsView(APIView):
    """
    API para estatísticas do dashboard - Cópia funcional da API do Core
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        user = request.user
        provedor = self._get_user_provedor(user)
        
        if not provedor:
            return Response({'error': 'Provedor não encontrado'}, status=400)
        
        # Importar modelos necessários
        from .models import Conversation, Contact, Message
        from django.db.models import Count, Q, Avg
        from django.utils import timezone
        from datetime import timedelta
        
        # Filtros baseados no provedor
        provedor_filter = Q(inbox__provedor=provedor)
        
        # Estatísticas de conversas
        total_conversas = Conversation.objects.filter(provedor_filter).count()
        conversas_abertas = Conversation.objects.filter(provedor_filter, status='open').count()
        conversas_pendentes = Conversation.objects.filter(provedor_filter, status='pending').count()
        conversas_resolvidas = Conversation.objects.filter(provedor_filter, status='closed').count() + Conversation.objects.filter(provedor_filter, status='resolved').count()
        conversas_em_andamento = conversas_abertas
        
        # Estatísticas de contatos únicos
        contatos_unicos = Contact.objects.filter(provedor=provedor).count()
        contatos_bloqueados_atender = Contact.objects.filter(provedor=provedor, bloqueado_atender=True).count()
        contatos_bloqueados_disparos = Contact.objects.filter(provedor=provedor, bloqueado_disparos=True).count()
        
        # Estatísticas de mensagens (últimos 30 dias)
        data_30_dias_atras = timezone.now() - timedelta(days=30)
        mensagens_30_dias = Message.objects.filter(
            conversation__inbox__provedor=provedor,
            created_at__gte=data_30_dias_atras
        ).count()
        
        # Tempo de resposta real via CSATFeedback.response_time_minutes
        try:
            from django.db.models import Avg
            avg_response_minutes = (
                CSATFeedback.objects
                .filter(
                    provedor=provedor,
                    feedback_sent_at__gte=data_30_dias_atras,
                )
                .aggregate(avg=Avg('response_time_minutes'))
                .get('avg')
            ) or 0
        except Exception:
            avg_response_minutes = 0

        tempo_medio_resposta = f"{avg_response_minutes:.1f}min" if avg_response_minutes else "0min"
        tempo_primeira_resposta = tempo_medio_resposta
        
        # Taxa de resolução
        if total_conversas > 0:
            taxa_resolucao = f"{int((conversas_resolvidas / total_conversas) * 100)}%"
        else:
            taxa_resolucao = "0%"
        
        # Satisfação média - usar dados reais do CSAT
        try:
            from .csat_automation import CSATAutomationService
            # Usar função local para obter stats CSAT
            from .csat_service import CSATService
            csat_stats = CSATService.get_csat_stats(provedor, 30)
            satisfacao_media = f"{csat_stats.get('average_rating', 0.0):.1f}"
        except Exception:
            # Sem CSAT: não inventar valores
            satisfacao_media = "0.0"
        
        # Estatísticas por canal
        canais_stats = Conversation.objects.filter(provedor_filter).values(
            'inbox__channel_type'
        ).annotate(
            total=Count('id')
        ).order_by('-total')
        
        return Response({
            'provedor_id': provedor.id,
            'total_conversas': total_conversas,
            'conversas_abertas': conversas_abertas,
            'conversas_pendentes': conversas_pendentes,
            'conversas_resolvidas': conversas_resolvidas,
            'conversas_em_andamento': conversas_em_andamento,
            'contatos_unicos': contatos_unicos,
            'contatos_bloqueados_atender': contatos_bloqueados_atender,
            'contatos_bloqueados_disparos': contatos_bloqueados_disparos,
            'mensagens_30_dias': mensagens_30_dias,
            'tempo_medio_resposta': tempo_medio_resposta,
            'tempo_primeira_resposta': tempo_primeira_resposta,
            'taxa_resolucao': taxa_resolucao,
            'satisfacao_media': satisfacao_media,
            'canais': list(canais_stats),
            'atendentes': [],
            'atividades': []
        })
    
    def _get_user_provedor(self, user):
        """Buscar provedor do usuário"""
        if hasattr(user, 'provedor') and user.provedor:
            return user.provedor
        return user.provedores_admin.first()