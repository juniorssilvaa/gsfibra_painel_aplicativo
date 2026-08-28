from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.authentication import TokenAuthentication
from rest_framework.parsers import MultiPartParser, FormParser
from core.authentication import LoggedTokenAuthentication
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db import models
from django.conf import settings
from core.models import CompanyUser, User, Provedor, Canal, AuditLog, SystemConfig, Company, MensagemSistema, ChatbotFlow, UserReminder, ProviderGalleryImage
from core.serializers import UserSerializer, UserCreateSerializer, CanalSerializer, AuditLogSerializer, SystemConfigSerializer, ProvedorSerializer, CompanySerializer, MensagemSistemaSerializer, UserReminderSerializer, ProviderGalleryImageSerializer
from django.db.models import Q
from integrations.models import TelegramIntegration, EmailIntegration, WhatsAppIntegration, WebchatIntegration
from integrations.serializers import (
    TelegramIntegrationSerializer, EmailIntegrationSerializer,
    WhatsAppIntegrationSerializer, WebchatIntegrationSerializer
)
from integrations.email_service import email_manager
from integrations.asaas_service import AsaasService
from datetime import datetime
import asyncio
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse, FileResponse, Http404
import json
import tempfile
import traceback
from conversations.models import Contact, Conversation, Message, Inbox
from core.models import Company
from django.utils import timezone
from core.openai_service import openai_service
from core.models import Provedor
import requests
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
import traceback
import time
import random
import subprocess
import os
import logging
import django
from types import SimpleNamespace

logger = logging.getLogger(__name__)

from datetime import datetime, timedelta
from pathlib import Path


from django.views.decorators.http import require_http_methods

@require_http_methods(["GET", "HEAD"])
def health_view(request):
    """
    Health check endpoint - retorna 200 OK sem tocar no banco de dados
    """
    import json
    return HttpResponse(
        json.dumps({"status": "ok"}), 
        content_type="application/json", 
        status=200
    )


@require_http_methods(["GET"])
def sentry_test_view(request):
    """
    Endpoint para validar integração com Sentry.
    Produção (DEBUG=False): use ?key=<SENTRY_TEST_KEY> (defina SENTRY_TEST_KEY no .env).
    Desenvolvimento: aceita também requisições de localhost ou ?dsn=<DSN> em DEBUG.
    Gera um erro intencional que deve aparecer em Sentry > Issues.
    """
    from decouple import config
    # Usar valores carregados no startup (settings) – funciona em produção com DEBUG=False
    sentry_dsn = getattr(settings, 'SENTRY_DSN', '') or config('SENTRY_DSN', default='')
    # Em DEBUG, permitir passar DSN na URL para testar: ?dsn=https://...
    if not sentry_dsn and settings.DEBUG:
        sentry_dsn = (request.GET.get('dsn') or '').strip()
    test_key = getattr(settings, 'SENTRY_TEST_KEY', '') or config('SENTRY_TEST_KEY', default='')
    key_param = request.GET.get('key', '')

    if not sentry_dsn:
        return JsonResponse({
            "ok": False,
            "message": "Sentry não está configurado. Defina SENTRY_DSN no .env ou use ?dsn=<seu_dsn> (apenas em DEBUG)."
        }, status=400)

    # Se DSN veio da URL (DEBUG), inicializar Sentry para este processo
    if settings.DEBUG and request.GET.get('dsn') and not getattr(settings, 'SENTRY_DSN', ''):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.django import DjangoIntegration
            sentry_sdk.init(dsn=sentry_dsn, integrations=[DjangoIntegration()])
        except Exception as e:
            logger.exception("Erro ao inicializar Sentry com DSN da URL")

    # Permitir: DEBUG, ou chave correta, ou requisição de localhost (para testes)
    remote = request.META.get('REMOTE_ADDR', '') or request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    is_localhost = remote in ('127.0.0.1', '::1', 'localhost', '')
    if not settings.DEBUG and not is_localhost and (not test_key or key_param != test_key):
        return JsonResponse({
            "ok": False,
            "message": "Não autorizado. Use ?key=<SENTRY_TEST_KEY> ou ative DEBUG."
        }, status=403)

    # Enviar mensagem de teste para Sentry (aparece em Issues como mensagem)
    try:
        import sentry_sdk
        sentry_sdk.capture_message(
            "Teste Sentry NioChat - validação da integração",
            level="info"
        )
    except Exception as e:
        logger.exception("Erro ao enviar mensagem de teste ao Sentry")

    # Gerar exceção intencional para aparecer em Sentry > Issues
    raise ValueError("Teste Sentry NioChat - erro intencional para validar integração")


def changelog_view(request):
    """
    Retorna o conteúdo do CHANGELOG.json
    """
    try:
        # Tentar múltiplos caminhos possíveis
        # BASE_DIR aponta para backend/, então precisamos subir mais um nível para a raiz
        base_path = Path(settings.BASE_DIR)
        possible_paths = [
            base_path.parent / 'CHANGELOG.json',  # Raiz do projeto (Prioridade)
            base_path.parent / '.github' / 'CHANGELOG.json',  # .github/CHANGELOG.json
            base_path / 'CHANGELOG.json',  # backend/CHANGELOG.json
            Path(__file__).parent.parent.parent.parent / 'CHANGELOG.json',
        ]
        
        changelog_data = None
        for changelog_path in possible_paths:
            if changelog_path.exists():
                with open(changelog_path, 'r', encoding='utf-8') as f:
                    changelog_data = json.load(f)
                break
        
        if changelog_data:
            return JsonResponse(changelog_data, safe=False)
        else:
            # Retornar estrutura vazia se não encontrar
            return JsonResponse({
                "versions": [],
                    "current_version": "2.38.1"
            }, safe=False)
    except Exception as e:
        logger.error(f'Erro ao carregar changelog: {e}')
        # Retornar estrutura vazia em caso de erro
        return JsonResponse({
            "versions": [],
            "current_version": "2.38.1"
        }, safe=False)


@require_http_methods(["GET"])
@csrf_exempt
def supabase_config_view(request):
    """
    Retorna as configurações públicas do Supabase para o frontend
    Apenas configurações públicas (URL e ANON_KEY) - nunca SERVICE_ROLE_KEY
    Endpoint público (sem autenticação necessária)
    """
    try:
        supabase_url = getattr(settings, 'SUPABASE_URL', '').rstrip('/')
        supabase_anon_key = getattr(settings, 'SUPABASE_ANON_KEY', '')
        
        if not supabase_url or not supabase_anon_key:
            return JsonResponse({
                'error': 'Supabase não configurado',
                'supabase_url': None,
                'supabase_anon_key': None
            }, status=503)
        
        return JsonResponse({
            'supabase_url': supabase_url,
            'supabase_anon_key': supabase_anon_key
        })
    except Exception as e:
        logger.error(f'Erro ao retornar configuração do Supabase: {e}')
        return JsonResponse({
            'error': 'Erro ao buscar configuração',
            'supabase_url': None,
            'supabase_anon_key': None
        }, status=500)


def process_sent_message(data, msg_data, chatid_full, clean_instance, uazapi_url, uazapi_token):
    """
    Processa mensagens enviadas pelo sistema para salvar external_id e atualizar file_url com URL real do WhatsApp
    """
    # Importar data aqui para ter acesso ao payload completo
    from django.http import JsonResponse
    try:
        # Extrair external_id da mensagem enviada
        external_id = msg_data.get('id') or msg_data.get('messageid')
        
        if not external_id:
            return JsonResponse({'status': 'ignored', 'reason': 'no external_id'}, status=200)
        
        # Buscar conversa existente
        phone = chatid_full.replace('@s.whatsapp.net', '').replace('@c.us', '')
        
        # Buscar contato
        contact = Contact.objects.filter(phone=phone).first()
        if not contact:
            return JsonResponse({'status': 'ignored', 'reason': 'contact not found'}, status=200)
        
        # Buscar conversa
        conversation = Conversation.objects.filter(contact=contact).first()
        if not conversation:
            return JsonResponse({'status': 'ignored', 'reason': 'conversation not found'}, status=200)
        
        # Buscar mensagem por external_id primeiro (mais preciso)
        recent_message = None
        if external_id:
            recent_message = Message.objects.filter(
                conversation=conversation,
                external_id=external_id,
                is_from_customer=False
            ).first()
            # Se não encontrou por external_id, tentar buscar por track_id (ID da mensagem local)
            if not recent_message:
                # Buscar track_id em diferentes locais do payload
                track_id = (msg_data.get('track_id') or 
                           (data.get('message', {}).get('track_id') if data else None) or
                           (data.get('track_id') if data else None))
                
                if track_id:
                    try:
                        track_id_int = int(track_id)
                        # track_id contém o ID da mensagem local
                        # Primeiro tentar buscar na conversa específica
                        recent_message = Message.objects.filter(
                            id=track_id_int,
                            conversation=conversation,
                            is_from_customer=False
                        ).first()
                        
                        # Se não encontrou na conversa, buscar em qualquer conversa (pode ser problema de conversa)
                        if not recent_message:
                            recent_message = Message.objects.filter(
                                id=track_id_int,
                                is_from_customer=False
                            ).first()
                        
                        # Se ainda não encontrou, verificar se a mensagem existe e usar mesmo que esteja em outra conversa
                        if not recent_message:
                            try:
                                msg_exists = Message.objects.filter(id=track_id_int).exists()
                                if msg_exists:
                                    msg_any = Message.objects.get(id=track_id_int)
                                    # Se encontrou mas está em outra conversa, usar mesmo assim se for documento
                                    if msg_any.message_type == 'document':
                                        recent_message = msg_any
                            except Exception:
                                pass
                    except (ValueError, TypeError):
                        pass
                    except Message.DoesNotExist:
                        pass
        
        # Se não encontrou por external_id, buscar mensagem mais recente
        # (webhook geralmente chega em poucos segundos após o envio)
        if not recent_message:
            # Buscar TODAS as mensagens dos últimos 2 minutos (aumentar janela de tempo)
            # A mensagem pode já ter external_id se foi atualizada por outro processo
            two_minutes_ago = timezone.now() - timedelta(minutes=2)
            all_recent = Message.objects.filter(
                conversation=conversation,
                is_from_customer=False,
                created_at__gte=two_minutes_ago
            ).order_by('-created_at')
            
            recent_message = all_recent.first()
            
            # Se ainda não encontrou, tentar buscar por file_name se disponível no payload
            if not recent_message:
                message_type = msg_data.get('messageType') or msg_data.get('type', '')
                content = {}
                if isinstance(msg_data.get('content'), dict):
                    content = msg_data.get('content', {})
                elif data and 'message' in data:
                    message_obj = data.get('message', {})
                    if isinstance(message_obj, dict) and isinstance(message_obj.get('content'), dict):
                        content = message_obj.get('content', {})
                
                file_name = None
                if isinstance(content, dict):
                    file_name = content.get('fileName') or content.get('filename')
                
                if file_name and message_type in ['DocumentMessage', 'document']:
                    # Buscar mensagem pelo nome do arquivo nos últimos 2 minutos
                    two_minutes_ago = timezone.now() - timedelta(minutes=2)
                    recent_message = Message.objects.filter(
                        conversation=conversation,
                        is_from_customer=False,
                        created_at__gte=two_minutes_ago,
                        file_name=file_name
                    ).order_by('-created_at').first()
        
        # Se ainda não encontrou, buscar mensagem mais recente (fallback)
        if not recent_message:
            recent_message = Message.objects.filter(
                conversation=conversation,
                is_from_customer=False
            ).order_by('-created_at').first()
        
        if recent_message:
            # Atualizar external_id na mensagem
            recent_message.external_id = external_id
            
            # Verificar se é uma mensagem de mídia/documento e extrair URL real do WhatsApp
            message_type = msg_data.get('messageType') or msg_data.get('type', '')
            # Buscar content em diferentes locais do payload
            content = {}
            # Tentar 1: msg_data.content (estrutura direta)
            if isinstance(msg_data.get('content'), dict):
                content = msg_data.get('content', {})
            # Tentar 2: data.message.content (estrutura do webhook Uazapi - mais comum)
            if (not content or not isinstance(content, dict) or not content.get('URL')) and data:
                message_obj = data.get('message', {})
                if isinstance(message_obj, dict) and isinstance(message_obj.get('content'), dict):
                    content = message_obj.get('content', {})
            
            # Se for documento, imagem, vídeo ou áudio, tentar extrair URL real do WhatsApp
            if message_type in ['DocumentMessage', 'ImageMessage', 'VideoMessage', 'AudioMessage'] or message_type in ['document', 'image', 'video', 'audio', 'media']:
                # Extrair URL do conteúdo se disponível
                whatsapp_url = None
                file_name = None
                file_size = None
                
                if isinstance(content, dict):
                    # URL real do WhatsApp (campo URL no content)
                    whatsapp_url = content.get('URL')
                    # Nome do arquivo
                    file_name = content.get('fileName') or content.get('filename')
                    # Tamanho do arquivo
                    file_size = content.get('fileLength') or content.get('file_size')
                
                
                # Se encontrou URL do WhatsApp, atualizar file_url
                if whatsapp_url:
                    recent_message.file_url = whatsapp_url
                    # Atualizar additional_attributes para manter URL do WhatsApp
                    additional_attrs = recent_message.additional_attributes or {}
                    additional_attrs['whatsapp_file_url'] = whatsapp_url
                    recent_message.additional_attributes = additional_attrs
                
                # Atualizar file_name se disponível
                if file_name:
                    recent_message.file_name = file_name
                
                # Atualizar file_size se disponível
                if file_size:
                    recent_message.file_size = file_size
            
            recent_message.save()
            
            return JsonResponse({'status': 'processed', 'external_id': external_id}, status=200)
        else:
            return JsonResponse({'status': 'ignored', 'reason': 'recent message not found'}, status=200)
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


def verify_and_normalize_number(chatid, uazapi_url, uazapi_token):
    """
    Verifica e normaliza um número usando o endpoint /chat/check da Uazapi
    """
    if not chatid or not uazapi_url or not uazapi_token:
        return chatid
    
    try:
        # Limpar o número para verificação
        clean_number = chatid.replace('@s.whatsapp.net', '').replace('@c.us', '')
        
        # Construir URL do endpoint /chat/check
        check_url = uazapi_url.replace('/send/text', '/chat/check')
        
        # Payload para verificação
        payload = {
            'numbers': [clean_number]
        }
        
        # Fazer requisição para verificar o número
        response = requests.post(
            check_url,
            headers={
                'token': uazapi_token,
                'Content-Type': 'application/json'
            },
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Verificar se o número foi encontrado
            if result and isinstance(result, list) and len(result) > 0:
                number_info = result[0]
                
                # Se o número foi verificado, usar o jid retornado
                if number_info.get('isInWhatsapp', False):
                    verified_jid = number_info.get('jid', '')
                    if verified_jid:
                        return verified_jid
    except Exception as e:
        pass
    
    # Se não conseguir verificar, retornar o número original
    return chatid


class TelegramIntegrationViewSet(viewsets.ModelViewSet):
    queryset = TelegramIntegration.objects.all()
    serializer_class = TelegramIntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'superadmin':
            return TelegramIntegration.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                return TelegramIntegration.objects.filter(provedor__in=provedores)
            return TelegramIntegration.objects.none()
    
    @action(detail=True, methods=['post'])
    def connect(self, request, pk=None):
        """Conectar integração Telegram"""
        integration = self.get_object()
        
        try:
            # Executar conexão de forma assíncrona
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            success = loop.run_until_complete(
                telegram_manager.start_integration(integration.id)
            )
            
            if success:
                return Response({'status': 'connected'})
            else:
                return Response(
                    {'error': 'Failed to connect'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def disconnect(self, request, pk=None):
        """Desconectar integração Telegram"""
        integration = self.get_object()
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            loop.run_until_complete(
                telegram_manager.stop_integration(integration.id)
            )
            
            return Response({'status': 'disconnected'})
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def send_message(self, request, pk=None):
        """Enviar mensagem via Telegram"""
        integration = self.get_object()
        chat_id = request.data.get('chat_id')
        content = request.data.get('content')
        reply_to_message_id = request.data.get('reply_to_message_id')
        
        if not chat_id or not content:
            return Response(
                {'error': 'chat_id and content are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            if integration.id in telegram_manager.services:
                service = telegram_manager.services[integration.id]
                
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                success = loop.run_until_complete(
                    service.send_message(chat_id, content, reply_to_message_id)
                )
                
                if success:
                    return Response({'status': 'message sent'})
                else:
                    return Response(
                        {'error': 'Failed to send message'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                return Response(
                    {'error': 'Integration not connected'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def status(self, request):
        user = request.user
        if user.user_type == 'superadmin':
            integrations = TelegramIntegration.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                integrations = TelegramIntegration.objects.filter(provedor__in=provedores)
            else:
                integrations = TelegramIntegration.objects.none()
        status_data = []
        for integration in integrations:
            status_data.append({
                'id': integration.id,
                'provedor': integration.provedor.nome,
                'phone_number': integration.phone_number,
                'is_active': integration.is_active,
                'is_connected': integration.is_connected,
                'is_running': integration.id in telegram_manager.services
            })
        return Response(status_data)


class EmailIntegrationViewSet(viewsets.ModelViewSet):
    queryset = EmailIntegration.objects.all()
    serializer_class = EmailIntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'superadmin':
            return EmailIntegration.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                return EmailIntegration.objects.filter(provedor__in=provedores)
            return EmailIntegration.objects.none()
    

    
    @action(detail=True, methods=['post'])
    def start_monitoring(self, request, pk=None):
        """Iniciar monitoramento de e-mails"""
        integration = self.get_object()
        
        try:
            email_manager.start_integration(integration.id)
            return Response({'status': 'monitoring started'})
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def stop_monitoring(self, request, pk=None):
        """Parar monitoramento de e-mails"""
        integration = self.get_object()
        
        try:
            email_manager.stop_integration(integration.id)
            return Response({'status': 'monitoring stopped'})
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def send_email(self, request, pk=None):
        """Enviar e-mail"""
        integration = self.get_object()
        to_email = request.data.get('to_email')
        subject = request.data.get('subject')
        content = request.data.get('content')
        reply_to_message_id = request.data.get('reply_to_message_id')
        
        if not to_email or not subject or not content:
            return Response(
                {'error': 'to_email, subject and content are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            if integration.id in email_manager.services:
                service = email_manager.services[integration.id]
                success = service.send_email(to_email, subject, content, reply_to_message_id)
                
                if success:
                    return Response({'status': 'email sent'})
                else:
                    return Response(
                        {'error': 'Failed to send email'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                return Response(
                    {'error': 'Integration not running'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'])
    def status(self, request):
        user = request.user
        if user.user_type == 'superadmin':
            integrations = EmailIntegration.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                integrations = EmailIntegration.objects.filter(provedor__in=provedores)
            else:
                integrations = EmailIntegration.objects.none()
        status_data = []
        for integration in integrations:
            status_data.append({
                'id': integration.id,
                'name': integration.name,
                'email': integration.email,
                'provider': integration.get_provider_display(),
                'provedor': integration.provedor.nome,
                'is_active': integration.is_active,
                'is_connected': integration.is_connected,
                'is_running': integration.id in email_manager.services
            })
        return Response(status_data)


class WhatsAppIntegrationViewSet(viewsets.ModelViewSet):
    queryset = WhatsAppIntegration.objects.all()
    serializer_class = WhatsAppIntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'superadmin':
            return WhatsAppIntegration.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                return WhatsAppIntegration.objects.filter(provedor__in=provedores)
            return WhatsAppIntegration.objects.none()


class WebchatIntegrationViewSet(viewsets.ModelViewSet):
    queryset = WebchatIntegration.objects.all()
    serializer_class = WebchatIntegrationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.user_type == 'superadmin':
            return WebchatIntegration.objects.all()
        else:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                return WebchatIntegration.objects.filter(provedor__in=provedores)
            return WebchatIntegration.objects.none()
    
    @action(detail=True, methods=['get'])
    def widget_script(self, request, pk=None):
        """Gerar script do widget de chat"""
        integration = self.get_object()
        
        script = f"""
        <script>
        (function() {{
            var chatWidget = document.createElement('div');
            chatWidget.id = 'niochat-widget';
            chatWidget.style.cssText = `
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 60px;
                height: 60px;
                background-color: {integration.widget_color};
                border-radius: 50%;
                cursor: pointer;
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 24px;
            `;
            chatWidget.innerHTML = '💬';
            
            chatWidget.onclick = function() {{
                // Abrir chat
                console.log('Chat widget clicked');
            }};
            
            document.body.appendChild(chatWidget);
        }})();
        </script>
        """
        
        return Response({
            'script': script,
            'widget_color': integration.widget_color,
            'welcome_message': integration.welcome_message
        })


# evolution_webhook completamente removido


@csrf_exempt
def webhook_evolution_uazapi(request):
    """Webhook para receber mensagens da Uazapi"""
    from datetime import datetime
    # Importar Conversation explicitamente para evitar UnboundLocalError
    from conversations.models import Conversation as ConversationModel
    
    if request.method != 'POST':
        logger.warning(f"[UAZAPI] Método {request.method} não permitido")
        return JsonResponse({'error': 'Método não permitido'}, status=405)
    
    try:
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'JSON inválido: {str(e)}'}, status=400)
        
        event_type = data.get('event') or data.get('EventType') or data.get('type')
        msg_data = data.get('data') or data.get('message', {})
        
# Inicializações para evitar F821 (linters) e tornar o fluxo mais explícito
        conversation = None
        contact = None
        msg = None
        
        # Extrair chatid corretamente
        chatid = msg_data.get('chatid', '')
        sender_lid = msg_data.get('sender_lid', '')
        
        # Verificar se o chatid é válido (não deve ser o número conectado)
        instance = data.get('instance') or data.get('owner')
        clean_instance = instance.replace('@s.whatsapp.net', '').replace('@c.us', '') if instance else ''
        clean_chatid = chatid.replace('@s.whatsapp.net', '').replace('@c.us', '') if chatid else ''
        
        if clean_chatid == clean_instance:
            return JsonResponse({'status': 'ignored', 'reason': 'message from connected number'}, status=200)
        
        # Buscar provedor e credenciais ANTES da verificação de números
        from core.models import Provedor
        
        # Buscar provedor CORRETO baseado na instance/owner
        # A instance/owner deve corresponder ao número conectado do provedor
        provedor = None
        
        # Buscar todos os provedores com credenciais da Uazapi
        provedores = Provedor.objects.filter(
            integracoes_externas__whatsapp_token__isnull=False
        )
        
        # Buscar o provedor correto baseado na instance
        for p in provedores:
            # Verificar se a instance corresponde ao número conectado do provedor
            provedor_instance = p.integracoes_externas.get('whatsapp_instance')
            if provedor_instance and clean_instance == provedor_instance.replace('@s.whatsapp.net', '').replace('@c.us', ''):
                provedor = p
                break
        
        # Se não encontrar por instance, tentar por token
        if not provedor:
            for p in provedores:
                uazapi_token = p.integracoes_externas.get('whatsapp_token')
                if uazapi_token and uazapi_token in str(data):
                    provedor = p
                    break
        
        # Se ainda não encontrar, usar o primeiro (fallback)
        if not provedor:
            provedor = provedores.first()
        
        if not provedor:
            return JsonResponse({'error': 'Nenhum provedor com credenciais da Uazapi encontrado'}, status=400)
        
        # Buscar token e url da UazAPI do provedor
        uazapi_token = provedor.integracoes_externas.get('whatsapp_token')
        uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
        
        if not uazapi_token or not uazapi_url:
            return JsonResponse({'error': 'Token ou URL não configurados no provedor'}, status=400)
        
        # Verificar e normalizar o número usando /chat/check
        if chatid and uazapi_url and uazapi_token:
            verified_chatid = verify_and_normalize_number(chatid, uazapi_url, uazapi_token)
            if verified_chatid != chatid:
                chatid = verified_chatid
        
        # Normalizar chatid usando a lógica do n8n
        if chatid and chatid.endswith('@s.whatsapp.net'):
            # Se termina com @s.whatsapp.net, pegar apenas o número
            chatid_clean = chatid.split('@')[0]
            chatid_full = chatid  # Manter o completo para envio
        else:
            # Se não termina com @s.whatsapp.net, adicionar
            chatid_clean = chatid
            chatid_full = f"{chatid}@s.whatsapp.net" if chatid else ''
        
        # Verificar se o chatid_clean é válido
        if not chatid_clean or chatid_clean == clean_instance:
            return JsonResponse({'status': 'ignored', 'reason': 'invalid chatid'}, status=200)
        
        # Verificar se é uma mensagem enviada pelo sistema (fromMe: true)
        fromMe = msg_data.get('fromMe', False)
        if fromMe:
            # Processar mensagem enviada para salvar external_id e atualizar URL do WhatsApp
            # Passar data completo para ter acesso a data.message.content
            return process_sent_message(data, msg_data, chatid_full, clean_instance, uazapi_url, uazapi_token)
        
        phone = chatid_full
        name = msg_data.get('pushName') or msg_data.get('senderName') or phone or 'Contato'
        instance = data.get('instance') or data.get('owner')

        # Extrair conteúdo da mensagem para a IA
        content = (
            msg_data.get('content') or
            msg_data.get('text') or
            msg_data.get('caption')
        )
        
        # Verificar se é uma mensagem respondida (reply) ANTES de converter content para string
        quoted_message = msg_data.get('quotedMessage') or msg_data.get('quoted_message') or msg_data.get('reply_to')
        reply_to_message_id = None
        reply_to_content = None
        
        # Verificar se há campo 'quoted' (novo formato)
        quoted_id = msg_data.get('quoted')
        if quoted_id:
            reply_to_message_id = quoted_id
        
        # Verificar se quotedMessage está dentro de content.contextInfo (novo formato)
        if not quoted_message and isinstance(content, dict):
            context_info = content.get('contextInfo', {})
            quoted_message = context_info.get('quotedMessage')
        
        if quoted_message:
            # Extrair informações da mensagem respondida
            if isinstance(quoted_message, dict):
                # Verificar se tem extendedTextMessage (novo formato)
                if 'extendedTextMessage' in quoted_message:
                    extended_msg = quoted_message['extendedTextMessage']
                    reply_to_content = extended_msg.get('text', 'Mensagem respondida')
                    if not reply_to_message_id:
                        reply_to_message_id = quoted_id or "ID_da_mensagem_respondida" # Fallback if quoted_id is also missing
                # Verificar se tem conversation (formato mais simples)
                elif 'conversation' in quoted_message:
                    reply_to_content = quoted_message.get('conversation', 'Mensagem respondida')
                    if not reply_to_message_id:
                        reply_to_message_id = quoted_id or "ID_da_mensagem_respondida"
                else:
                    reply_to_message_id = quoted_message.get('id') or quoted_message.get('messageId') or quoted_message.get('key', {}).get('id')
                    reply_to_content = quoted_message.get('text') or quoted_message.get('content') or quoted_message.get('caption')
            elif isinstance(quoted_message, str):
                reply_to_message_id = quoted_message
                reply_to_content = "Mensagem respondida"
            
        # Agora converter content para string se for um objeto
        if isinstance(content, dict) and 'text' in content:
            content = content['text']
        
        # Inicializar additional_attrs no início para evitar erros
        additional_attrs = {}
        
        # Detectar tipo de mensagem
        message_type = msg_data.get('type') or msg_data.get('messageType') or 'text'
        media_type = msg_data.get('mediaType') or msg_data.get('media_type')
        
        # Verificar se é uma mensagem de áudio baseada no conteúdo
        is_audio_message = False
        is_from_customer = True  # Por padrão, mensagens são do cliente
        if isinstance(content, dict) and content.get('mimetype', '').startswith('audio/'):
            is_audio_message = True
            message_type = 'audio'
        
        # Verificar se é uma reação
        if message_type == 'ReactionMessage' or message_type == 'reaction':
            # Para reações, não criar nova mensagem, apenas atualizar a mensagem original
            reaction_emoji = content
            
            # Extrair o ID da mensagem original de diferentes campos
            reaction_id = None
            
            # Tentar diferentes campos para encontrar o ID da mensagem original
            if 'reaction' in msg_data:
                reaction_id = msg_data['reaction']
            elif 'content' in msg_data and isinstance(msg_data['content'], dict):
                # Verificar se o content tem informações da mensagem original
                content_data = msg_data['content']
                if 'key' in content_data and 'ID' in content_data['key']:
                    reaction_id = content_data['key']['ID']
            
            # Se ainda não encontrou, tentar buscar pela mensagem mais recente do cliente
            if not reaction_id:
                try:
                    # Buscar a mensagem mais recente do cliente na conversa
                    recent_message = Message.objects.filter(
                        conversation=conversation,
                        is_from_customer=True
                    ).order_by('-created_at').first()
                    
                    if recent_message:
                        reaction_id = recent_message.external_id
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar por mensagens de áudio recentes
            if not reaction_id:
                try:
                    # Buscar mensagens de áudio recentes do cliente
                    audio_messages = Message.objects.filter(
                        conversation=conversation,
                        is_from_customer=True,
                        message_type__in=['audio', 'ptt']
                    ).order_by('-created_at')[:3]  # Últimas 3 mensagens de áudio
                    
                    for audio_msg in audio_messages:
                        # Verificar se o timestamp da reação é próximo ao da mensagem de áudio
                        reaction_timestamp = msg_data.get('messageTimestamp', 0)
                        message_timestamp = audio_msg.created_at.timestamp() * 1000  # Converter para milissegundos
                        
                        # Se a diferença for menor que 5 minutos (300000ms), usar esta mensagem
                        if abs(reaction_timestamp - message_timestamp) < 300000:
                            reaction_id = audio_msg.external_id
                            break
                            
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar pelo ID da reação (campo 'reaction')
            if not reaction_id:
                try:
                    reaction_target_id = msg_data.get('reaction')
                    if reaction_target_id:
                        # Buscar mensagem que contenha o ID da reação no external_id
                        original_message = Message.objects.filter(
                            conversation=conversation,
                            external_id__icontains=reaction_target_id
                        ).first()
                        
                        if original_message:
                            reaction_id = original_message.external_id
                            
                            # Tentar buscar em todas as conversas
                            global_message = Message.objects.filter(
                                external_id__icontains=reaction_target_id
                            ).first()
                            
                            if global_message:
                                # Se encontrou em outra conversa, usar essa conversa
                                conversation = global_message.conversation
                                reaction_id = global_message.external_id
                            
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar pelo messageid sem o prefixo
            if not reaction_id:
                try:
                    # Buscar mensagem pelo messageid sem o prefixo
                    messageid = msg_data.get('messageid')
                    if messageid:
                        # Tentar buscar pelo messageid completo
                        original_message = Message.objects.get(external_id=messageid)
                        reaction_id = messageid
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar pelo ID da reação
            if not reaction_id:
                try:
                    # Buscar mensagem pelo ID da reação
                    reaction_message_id = msg_data.get('id')
                    if reaction_message_id:
                        # Tentar buscar pelo ID da reação
                        original_message = Message.objects.get(external_id=reaction_message_id)
                        reaction_id = reaction_message_id
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar por diferentes formatos de ID
            if not reaction_id:
                try:
                    # Tentar buscar por ID sem prefixo
                    if 'ACEC0B4C35057C2EE3C83EF5F570C42F' in str(msg_data):
                        # Buscar por ID sem prefixo
                        messages = Message.objects.filter(
                            conversation=conversation,
                            external_id__icontains='ACEC0B4C35057C2EE3C83EF5F570C42F'
                        )
                        if messages.exists():
                            reaction_id = messages.first().external_id
                    
                    # Se ainda não encontrou, buscar pela mensagem mais recente de áudio
                    if not reaction_id:
                        audio_message = Message.objects.filter(
                            conversation=conversation,
                            message_type__in=['audio', 'ptt']
                        ).order_by('-created_at').first()
                        
                        if audio_message:
                            reaction_id = audio_message.external_id
                            
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar pela mensagem mais recente
            if not reaction_id:
                try:
                    # Buscar a mensagem mais recente na conversa
                    recent_message = Message.objects.filter(
                        conversation=conversation
                    ).order_by('-created_at').first()
                    
                    if recent_message:
                        reaction_id = recent_message.external_id
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar pelo ID da reação com prefixo
            if not reaction_id:
                try:
                    # Buscar pelo ID da reação com prefixo
                    reaction_id_with_prefix = f"{msg_data.get('owner')}:{msg_data.get('reaction')}"
                    
                    original_message = Message.objects.get(external_id=reaction_id_with_prefix)
                    reaction_id = reaction_id_with_prefix
                except Exception as e:
                    pass
            
            # Se ainda não encontrou, tentar buscar pelo ID da reação sem prefixo
            if not reaction_id:
                try:
                    # Buscar pelo ID da reação sem prefixo
                    reaction_id_without_prefix = msg_data.get('reaction')
                    
                    # Buscar mensagem que contenha o ID da reação (mais recente primeiro)
                    original_message = Message.objects.filter(
                        conversation=conversation,
                        external_id__icontains=reaction_id_without_prefix
                    ).order_by('-created_at').first()
                    
                    if original_message:
                        reaction_id = original_message.external_id
                except Exception as e:
                    pass
            
            if reaction_id:
                try:
                    # Buscar mensagem original pelo external_id exato
                    original_message = Message.objects.filter(external_id=reaction_id).first()
                    
                    # Se não encontrou, tentar buscar por external_id que contenha o reaction_id
                    if not original_message:
                        original_message = Message.objects.filter(
                            external_id__icontains=reaction_id
                        ).first()
                    
                    # Se ainda não encontrou, tentar buscar em todas as conversas
                    if not original_message:
                        original_message = Message.objects.filter(
                            external_id__icontains=reaction_id
                        ).first()
                    
                    if original_message:
                        # Usar a conversa da mensagem original
                        conversation = original_message.conversation
                    else:
                        return
                    
                    # Atualizar a mensagem original com a reação
                    if not original_message.additional_attributes:
                        original_message.additional_attributes = {}
                    
                    # Adicionar reação aos atributos
                    if 'reactions' not in original_message.additional_attributes:
                        original_message.additional_attributes['reactions'] = []
                    
                    # Adicionar reações recebidas do cliente
                    if 'received_reactions' not in original_message.additional_attributes:
                        original_message.additional_attributes['received_reactions'] = []
                    
                    # Definir phone_number para reações
                    phone_number = chatid_clean
                    
                    # Verificar se já existe reação do mesmo usuário
                    user_reaction = None
                    for reaction in original_message.additional_attributes['reactions']:
                        if reaction.get('user_id') == phone_number:
                            user_reaction = reaction
                            break
                    
                    # Se a reação está vazia, remover a reação existente
                    if not reaction_emoji or reaction_emoji.strip() == "":
                        if user_reaction:
                            original_message.additional_attributes['reactions'].remove(user_reaction)
                    else:
                        if user_reaction:
                            # Atualizar reação existente
                            user_reaction['emoji'] = reaction_emoji
                            user_reaction['timestamp'] = msg_data.get('messageTimestamp', 0)
                        else:
                            # Adicionar nova reação
                            original_message.additional_attributes['reactions'].append({
                                'user_id': phone_number,
                                'emoji': reaction_emoji,
                                'timestamp': msg_data.get('messageTimestamp', 0)
                            })
                    
                    # Gerenciar reações recebidas do cliente
                    if reaction_emoji and reaction_emoji.strip() != "":
                        # Verificar se já existe reação do cliente
                        existing_customer_reaction = None
                        for reaction in original_message.additional_attributes['received_reactions']:
                            if reaction.get('from_customer', False):
                                existing_customer_reaction = reaction
                                break
                        
                        if existing_customer_reaction:
                            # Atualizar reação existente do cliente
                            existing_customer_reaction['emoji'] = reaction_emoji
                            existing_customer_reaction['timestamp'] = timezone.now().isoformat()
                        else:
                            # Adicionar nova reação do cliente
                            original_message.additional_attributes['received_reactions'].append({
                                'emoji': reaction_emoji,
                                'timestamp': timezone.now().isoformat(),
                                'from_customer': True
                            })
                    else:
                        # Se a reação está vazia, limpar todas as reações recebidas do cliente
                        original_message.additional_attributes['received_reactions'] = [
                            reaction for reaction in original_message.additional_attributes['received_reactions']
                            if not reaction.get('from_customer', False)
                        ]
                    
                    original_message.save()
                    
                    # Enviar notificação WebSocket para atualizar o frontend
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    
                    channel_layer = get_channel_layer()
                    if channel_layer:
                        async_to_sync(channel_layer.group_send)(
                            f'conversation_{conversation.id}',
                            {
                                'type': 'message_updated',
                                'action': 'reaction_updated',
                                'message_id': original_message.id,
                                'reaction_emoji': reaction_emoji
                            }
                        )
                    
                    return JsonResponse({'status': 'reaction_processed'}, status=200)
                    
                except Message.DoesNotExist:
                    # Se não encontrar a mensagem original, ignorar a reação
                    return JsonResponse({'status': 'reaction_ignored'}, status=200)
                except Exception as e:
                    # Se houver erro, ignorar a reação
                    return JsonResponse({'status': 'reaction_error'}, status=200)
            else:
                return JsonResponse({'status': 'reaction_ignored'}, status=200)
        
        # Para mensagens de mídia, não usar o JSON bruto como conteúdo
        if (message_type in ['audio', 'image', 'video', 'document', 'sticker', 'ptt', 'media'] or
            message_type in ['AudioMessage', 'ImageMessage', 'VideoMessage', 'DocumentMessage'] or
            media_type in ['ptt', 'audio', 'image', 'video', 'document', 'sticker'] or
            is_audio_message):
            
            # Se o conteúdo for um JSON (objeto), não usar como texto
            if isinstance(content, dict) or (isinstance(content, str) and content.startswith('{')):
                content = None
            
            # Definir conteúdo apropriado para cada tipo de mídia
            if not content:
                if (message_type in ['audio', 'ptt', 'AudioMessage'] or 
                    media_type in ['ptt', 'audio'] or is_audio_message):
                    content = 'Mensagem de voz'
                elif message_type in ['image', 'ImageMessage'] or media_type == 'image':
                    content = 'Imagem'
                elif message_type in ['sticker', 'StickerMessage'] or media_type == 'sticker':
                    content = 'Figurinha'
                elif message_type in ['video', 'VideoMessage'] or media_type == 'video':
                    content = 'Vídeo'
                elif message_type in ['document', 'DocumentMessage'] or media_type == 'document':
                    # Preservar content original para processamento de PDF
                    original_content = content
                    content = 'Documento'
                    # Extrair thumbnail e pageCount do msg_data se for PDF
                    if isinstance(msg_data, dict) and 'content' in msg_data:
                        msg_content = msg_data['content']
                        if isinstance(msg_content, dict):
                            # Extrair thumbnail em base64 se disponível
                            if 'JPEGThumbnail' in msg_content:
                                additional_attrs['pdf_thumbnail'] = msg_content['JPEGThumbnail']
                            # Extrair número de páginas se disponível
                            if 'pageCount' in msg_content:
                                additional_attrs['pages'] = msg_content['pageCount']
                            # Extrair tamanho do arquivo se disponível
                            if 'fileLength' in msg_content:
                                additional_attrs['file_size'] = msg_content['fileLength']
                else:
                    content = f'Mídia ({message_type})'
        else:
            # Para mensagens de texto, se não houver conteúdo, usar placeholder
            if not content:
                content = 'Mensagem de texto'

        # Filtrar apenas eventos de mensagem
        mensagem_eventos = ['message', 'messages', 'message_received', 'incoming_message', 'mensagem', 'mensagens']
        delete_eventos = ['delete', 'deleted', 'message_delete', 'message_deleted', 'revoke', 'revoked', 'remove', 'removed']
        
        event_type_lower = str(event_type).lower()
        
        # Verificar se é um evento de exclusão
        if event_type_lower in delete_eventos:
            # Extrair ID da mensagem deletada de diferentes possíveis locais
            deleted_message_id = (
                msg_data.get('id') or msg_data.get('messageid') or 
                msg_data.get('key', {}).get('id') or
                msg_data.get('messageId') or
                msg_data.get('message_id') or
                data.get('id') or
                data.get('messageId') or
                data.get('message_id')
            )
            
            if deleted_message_id:
                
                # Buscar a mensagem no banco de dados pelo external_id
                try:
                    message = Message.objects.get(external_id=deleted_message_id)
                    
                    # Marcar como deletada
                    additional_attrs = message.additional_attributes or {}
                    additional_attrs['status'] = 'deleted'
                    additional_attrs['deleted_at'] = str(datetime.now())
                    additional_attrs['deleted_by'] = 'client'
                    message.additional_attributes = additional_attrs
                    message.save()
                    
                    # Emitir evento WebSocket
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    channel_layer = get_channel_layer()
                    from conversations.serializers import MessageSerializer
                    message_data = MessageSerializer(message).data
                    
                    async_to_sync(channel_layer.group_send)(
                        f"conversation_{message.conversation.id}",
                        {
                            "type": "chat_message",
                            "message": message_data,
                            "sender": None,
                            "timestamp": message.updated_at.isoformat(),
                        }
                    )
                    
                    return JsonResponse({'status': 'message_deleted'}, status=200)
                    
                except Message.DoesNotExist:
                    # Tentar buscar por outros campos
                    try:
                        # Buscar por ID da mensagem
                        message = Message.objects.get(id=deleted_message_id)
                        
                        # Marcar como deletada
                        additional_attrs = message.additional_attributes or {}
                        additional_attrs['status'] = 'deleted'
                        additional_attrs['deleted_at'] = str(datetime.now())
                        additional_attrs['deleted_by'] = 'client'
                        message.additional_attributes = additional_attrs
                        message.save()
                        
                        # Emitir evento WebSocket
                        from channels.layers import get_channel_layer
                        from asgiref.sync import async_to_sync
                        channel_layer = get_channel_layer()
                        from conversations.serializers import MessageSerializer
                        message_data = MessageSerializer(message).data
                        
                        async_to_sync(channel_layer.group_send)(
                            f"conversation_{message.conversation.id}",
                            {
                                "type": "chat_message",
                                "message": message_data,
                                "sender": None,
                                "timestamp": message.updated_at.isoformat(),
                            }
                        )
                        
                        return JsonResponse({'status': 'message_deleted'}, status=200)
                        
                    except Message.DoesNotExist:
                        return JsonResponse({'status': 'message_not_found'}, status=200)
            else:
                return JsonResponse({'status': 'no_message_id'}, status=200)
        
        # Verificar se é um evento de mensagem normal
        if event_type_lower not in mensagem_eventos:
            # Ignorar eventos que não são de mensagem
            return JsonResponse({'status': 'ignored'}, status=200)

        # 4. Detectar se é mensagem da IA (enviada pelo próprio número conectado)
        sender = msg_data.get('sender') or msg_data.get('from') or ''
        is_ai_response = False
        sender_clean = ''
        if sender:
            sender_clean = sender.replace('@s.whatsapp.net', '').replace('@c.us', '')
            if sender_clean == clean_instance:
                is_ai_response = True
        if is_ai_response:
            return JsonResponse({'status': 'ignored', 'reason': 'AI response message'}, status=200)

        # Não responder mensagens enviadas pelo próprio número do bot (exceto para áudio)
        bot_number = str(instance)
        chatid = msg_data.get('chatid', '')
        sender_lid = msg_data.get('sender_lid', '')
        
        # Verificar se a mensagem está sendo enviada para o número conectado
        is_sent_to_bot = False
        if bot_number:
            # Limpar números para comparação
            clean_bot_number = bot_number.replace('@s.whatsapp.net', '').replace('@c.us', '')
            clean_chatid = chatid.replace('@s.whatsapp.net', '').replace('@c.us', '') if chatid else ''
            clean_sender_lid = sender_lid.replace('@lid', '').replace('@c.us', '') if sender_lid else ''
            
            # Verificar se está sendo enviado para o bot
            if (clean_chatid == clean_bot_number) or (clean_sender_lid == clean_bot_number):
                is_sent_to_bot = True
                return JsonResponse({'status': 'ignored', 'reason': 'message sent to connected number'}, status=200)

        # 2. Buscar ou criar contato
        # Extrair chatid e sender_lid da mensagem
        chatid = msg_data.get('chatid', '')
        sender_lid = msg_data.get('sender_lid', '')
        
        # Extrair nome e avatar do webhook
        # Prioridade: senderName, name, wa_contactName (conforme solicitado)
        nome_evo = (
            msg_data.get('senderName') or 
            data.get('chat', {}).get('name') or 
            data.get('chat', {}).get('wa_contactName')
        )
        # Avatar: procurar em msg_data.avatar, chat.image, chat.imagePreview
        avatar_evo = (
            msg_data.get('avatar') or 
            data.get('chat', {}).get('image') or
            data.get('chat', {}).get('imagePreview')
        )
        
        # Usar chatid_clean para o phone_number (evitar duplicação)
        phone_number = chatid_clean
        
        # Buscar contato existente por phone (que agora é o chatid limpo)
        contact = None
        if phone_number:
            # Buscar por phone_number exato primeiro
            contact = Contact.objects.filter(phone=phone_number, provedor=provedor).first()
            
            # Se não encontrou, buscar por números similares (variações de dígitos)
            if not contact:
                # Criar variações do número para busca
                phone_variations = [
                    phone_number,                    # número original
                    phone_number[1:],               # sem primeiro dígito  
                    phone_number[2:],               # sem dois primeiros dígitos
                    f"55{phone_number[2:]}",        # adicionar 55 
                    f"559{phone_number[3:]}",       # adicionar 559
                    f"5594{phone_number[4:]}",      # adicionar 5594
                ]
                
                # Buscar contatos que tenham números similares
                for variation in phone_variations:
                    if len(variation) >= 8:  # apenas variações válidas
                        contact = Contact.objects.filter(
                            phone__endswith=variation[-8:],  # últimos 8 dígitos
                            provedor=provedor
                        ).first()
                        if contact:
                            break
            
            # Se não encontrou, buscar por chatid nos additional_attributes
            if not contact:
                contact = Contact.objects.filter(
                    additional_attributes__chatid__icontains=phone_number,
                    provedor=provedor
                ).first()
            
            # Se ainda não encontrou, buscar por sender_lid (apenas como fallback)
            if not contact and sender_lid:
                contact = Contact.objects.filter(
                    additional_attributes__sender_lid=sender_lid,
                    provedor=provedor
                ).first()
        
        if contact:
            # Atualizar contato existente
            updated = False
            if nome_evo and contact.name != nome_evo:
                contact.name = nome_evo
                updated = True
            if avatar_evo and contact.avatar != avatar_evo:
                contact.avatar = avatar_evo
                updated = True
            
            # Atualizar phone se mudou
            if phone_number and contact.phone != phone_number:
                contact.phone = phone_number
                updated = True
            
            # Atualizar additional_attributes se necessário
            if sender_lid and contact.additional_attributes.get('sender_lid') != sender_lid:
                contact.additional_attributes['sender_lid'] = sender_lid
                updated = True
            
            if updated:
                contact.save()
                
            # Buscar foto do perfil sempre (novos e existentes)
            if chatid_clean and uazapi_token and uazapi_url:
                try:
                    # Construir URL para o endpoint /chat/details
                    base_url = uazapi_url.rstrip('/')
                    chat_details_url = f"{base_url}/chat/details"
                    
                    payload = {
                        'number': chatid_clean
                    }
                    
                    import requests as http_requests
                    response = http_requests.post(
                        chat_details_url,
                        headers={
                            'token': uazapi_token,
                            'Content-Type': 'application/json'
                        },
                        json=payload,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        chat_data = response.json()
                        
                        # Verificar se há foto do perfil (sempre atualizar)
                        if 'image' in chat_data and chat_data['image']:
                            contact.avatar = chat_data['image']
                            contact.save()
                            
                        # Verificar se há nome verificado (sempre atualizar se diferente)
                        if 'wa_name' in chat_data and chat_data['wa_name'] and contact.name != chat_data['wa_name']:
                            contact.name = chat_data['wa_name']
                            contact.save()
                        elif 'name' in chat_data and chat_data['name'] and contact.name != chat_data['name']:
                            contact.name = chat_data['name']
                            contact.save()
                            
                except Exception as e:
                    pass
        else:
            # Criar novo contato
            contact = Contact.objects.create(
                phone=phone_number or '',
                provedor=provedor,
                name=nome_evo or phone_number or 'Contato Desconhecido',
                additional_attributes={
                    'instance': instance,
                    'event': event_type,
                    'chatid': chatid_full,  # Salvar chatid completo nos additional_attributes
                    'sender_lid': sender_lid
                }
            )
            # Buscar foto do perfil usando o endpoint /chat/details da Uazapi (sempre)
            if chatid_clean and uazapi_token and uazapi_url:
                try:
                    # Construir URL para o endpoint /chat/details
                    base_url = uazapi_url.rstrip('/')
                    chat_details_url = f"{base_url}/chat/details"
                    
                    payload = {
                        'number': chatid_clean
                    }
                    
                    import requests as http_requests
                    response = http_requests.post(
                        chat_details_url,
                        headers={
                            'token': uazapi_token,
                            'Content-Type': 'application/json'
                        },
                        json=payload,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        chat_data = response.json()
                        
                        # Verificar se há foto do perfil
                        if 'image' in chat_data and chat_data['image']:
                            contact.avatar = chat_data['image']
                            contact.save()
                            
                        # Verificar se há nome verificado
                        if 'wa_name' in chat_data and chat_data['wa_name']:
                            contact.name = chat_data['wa_name']
                            contact.save()
                        elif 'name' in chat_data and chat_data['name']:
                            contact.name = chat_data['name']
                            contact.save()
                            
                except Exception as e:
                    pass

        # 3. Buscar ou criar inbox específica para esta instância
        inbox, _ = Inbox.objects.get_or_create(
            name=f'WhatsApp {instance}',
            channel_type='whatsapp',
            provedor=provedor,
            defaults={
                'additional_attributes': {
                    'instance': instance,
                    'channel_type': 'whatsapp'
                }
            }
        )
        
        # Buscar conversa ativa primeiro, depois qualquer conversa
        # Primeiro, buscar conversa ativa (não fechada)
        existing_conversation = ConversationModel.objects.filter(
            contact=contact,
            inbox__channel_type='whatsapp',
            status__in=['open', 'snoozed', 'pending']  # Apenas conversas ativas
        ).first()
        
        # Se não encontrou conversa ativa, buscar qualquer conversa (incluindo fechadas)
        if not existing_conversation:
            existing_conversation = ConversationModel.objects.filter(
                contact=contact,
                inbox__channel_type='whatsapp'
            ).first()
        
        if existing_conversation:
            # Verificar se a conversa está ativa
            if existing_conversation.status in ['open', 'snoozed', 'pending']:
                # Conversa está ativa - continuar usando a mesma
                conversation = existing_conversation
                if conversation.inbox != inbox:
                    conversation.inbox = inbox
                    conversation.save()
                # IMPORTANTE: Se está em 'pending', manter o status mesmo que a IA responda
                # Não alterar status nem atribuição quando está aguardando atendente/equipe
                conv_created = False
            else:
                # Conversa estava fechada - verificar se há CSAT pendente primeiro
                
                # Verificar se há CSAT pendente para esta conversa
                from conversations.models import CSATRequest
                csat_request = CSATRequest.objects.filter(
                    conversation=existing_conversation,
                    status='sent'
                ).first()
                
                if csat_request:
                        # Processar CSAT sem reabrir conversa
                        conversation = existing_conversation
                else:
                    # Limpar memória Redis da conversa anterior
                    try:
                        from core.redis_memory_service import redis_memory_service
                        redis_memory_service.clear_conversation_memory_sync(
                            provedor_id=existing_conversation.inbox.provedor_id if existing_conversation.inbox else None,
                            conversation_id=existing_conversation.id
                        )
                    except Exception as e:
                        pass
                    
                    # Criar nova conversa para novo atendimento
                    conversation = ConversationModel.objects.create(
                        contact=contact,
                        inbox=inbox,
                        status='snoozed',  # Nova conversa começa com IA
                    assignee=None,
                    additional_attributes={
                        'instance': instance,
                        'event': event_type
                    }
                )
                conv_created = True
        else:
            # Criar nova conversa
            conversation = ConversationModel.objects.create(
                contact=contact,
                inbox=inbox,
                status='snoozed',
                additional_attributes={
                    'instance': instance,
                    'event': event_type
                }
            )
            conv_created = True
        
        # 4. Extrair external_id da mensagem
        external_id = msg_data.get('id') or msg_data.get('key', {}).get('id') or msg_data.get('messageid')
        
        # 5. Processar mídia se for mensagem de mídia
        additional_attrs = {}
        if external_id:
            additional_attrs['external_id'] = external_id
        
        file_url = None
        
        if (message_type in ['audio', 'image', 'video', 'document', 'sticker', 'ptt', 'media'] or
            message_type in ['AudioMessage', 'ImageMessage', 'VideoMessage', 'DocumentMessage'] or
            media_type in ['ptt', 'audio', 'image', 'video', 'document', 'sticker'] or
            is_audio_message):
            
            # Tentar baixar o arquivo da Uazapi
            try:
                # Buscar URL de download da Uazapi
                download_url = None
                if uazapi_url and uazapi_token:
                    # Construir URL de download baseada na URL base
                    base_url = uazapi_url.replace('/send/text', '')
                    download_url = f"{base_url}/message/download"
                
                if download_url and uazapi_token:
                    # Baixar arquivo da Uazapi
                    import os
                    from django.conf import settings
                    import requests
                    
                    # Criar diretório para mídia
                    media_dir = os.path.join(settings.MEDIA_ROOT, 'messages', str(conversation.id))
                    os.makedirs(media_dir, exist_ok=True)
                    
                    # Determinar extensão e prefixo baseados no tipo de mídia
                    file_extension = '.mp3'  # Padrão para áudio
                    file_prefix = 'audio'
                    
                    if isinstance(content, dict) and content.get('mimetype'):
                        mimetype = content.get('mimetype')
                        if 'image' in mimetype:
                            file_extension = '.jpg'
                            file_prefix = 'image'
                        elif 'video' in mimetype:
                            file_extension = '.mp4'
                            file_prefix = 'video'
                        elif 'document' in mimetype or 'pdf' in mimetype:
                            file_extension = '.pdf'
                            file_prefix = 'document'
                        elif 'ogg' in mimetype:
                            file_extension = '.ogg'
                            file_prefix = 'audio'
                        elif 'opus' in mimetype:
                            file_extension = '.opus'
                            file_prefix = 'audio'
                        elif 'mp3' in mimetype:
                            file_extension = '.mp3'
                            file_prefix = 'audio'
                        elif 'wav' in mimetype:
                            file_extension = '.wav'
                            file_prefix = 'audio'
                        elif 'm4a' in mimetype:
                            file_extension = '.m4a'
                            file_prefix = 'audio'
                    else:
                        # Determinar baseado no tipo de mensagem
                        if message_type == 'image':
                            file_extension = '.jpg'
                            file_prefix = 'image'
                        elif message_type == 'video':
                            file_extension = '.mp4'
                            file_prefix = 'video'
                        elif message_type == 'document':
                            file_extension = '.pdf'
                            file_prefix = 'document'
                        elif message_type == 'audio' or is_audio_message:
                            file_extension = '.mp3'
                            file_prefix = 'audio'
                        else:
                            file_extension = '.mp3'
                            file_prefix = 'media'
                    
                    # Para áudios, sempre usar .mp3 para garantir compatibilidade
                    if message_type == 'audio' or is_audio_message:
                        file_extension = '.mp3'
                        file_prefix = 'audio'
                    
                    # Gerar nome do arquivo
                    import time
                    timestamp = int(time.time() * 1000)
                    filename = f"{file_prefix}_{timestamp}{file_extension}"
                    file_path = os.path.join(media_dir, filename)
                    
                    # Preparar payload para download conforme documentação da Uazapi
                    message_id = msg_data.get('id') or msg_data.get('key', {}).get('id') or msg_data.get('messageid')
                    if message_id:
                        download_payload = {
                            'id': message_id,
                            'return_base64': False,  # Queremos o arquivo, não base64
                            'return_link': True,     # Queremos a URL pública
                        }
                        
                        # Para áudios, especificar formato
                        if message_type == 'audio' or is_audio_message:
                            download_payload['generate_mp3'] = True
                            # Forçar conversão para MP3 para garantir compatibilidade
                            download_payload['mimetype'] = 'audio/mpeg'
                            download_payload['format'] = 'mp3'  # Adicionar formato explícito
                        
                        download_response = requests.post(
                            download_url,
                            headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                            json=download_payload,
                            timeout=15  # Reduzir timeout
                        )
                        
                        if download_response.status_code == 200:
                            try:
                                response_data = download_response.json()
                                
                                # Verificar se temos fileURL na resposta
                                if 'fileURL' in response_data:
                                    file_url = response_data['fileURL']
                                    
                                    # Preparar atributos adicionais (manter external_id existente)
                                    additional_attrs.update({
                                        'file_url': file_url,
                                        'file_name': filename,
                                        'message_type': message_type,
                                        'original_message_id': message_id,
                                        'mimetype': response_data.get('mimetype', ''),
                                        'uazapi_response': response_data
                                    })
                                    
                                    # Baixar arquivo de forma otimizada
                                    try:
                                        # Baixar arquivo do UazAPI com timeout reduzido
                                        file_response = requests.get(file_url, timeout=15)
                                        
                                        if file_response.status_code == 200:
                                            # Salvar arquivo localmente
                                            with open(file_path, 'wb') as f:
                                                f.write(file_response.content)
                                            
                                            # Conversão otimizada para MP3
                                            if filename.endswith('.webm'):
                                                try:
                                                    import subprocess
                                                    mp3_path = file_path.replace('.webm', '.mp3')
                                                    mp3_filename = filename.replace('.webm', '.mp3')
                                                    
                                                    # Converter usando ffmpeg com timeout
                                                    result = subprocess.run([
                                                        'ffmpeg', '-i', file_path, 
                                                        '-acodec', 'libmp3lame', 
                                                        '-ab', '128k', 
                                                        '-y', mp3_path
                                                    ], capture_output=True, text=True, timeout=30)
                                                    
                                                    if result.returncode == 0:
                                                        # Usar o arquivo MP3 em vez do WebM
                                                        file_path = mp3_path
                                                        filename = mp3_filename
                                                        additional_attrs['file_path'] = mp3_path
                                                        additional_attrs['file_size'] = os.path.getsize(mp3_path)
                                                        # Usar URL pública acessível
                                                        additional_attrs['local_file_url'] = f"/api/media/messages/{conversation.id}/{mp3_filename}/"
                                                except subprocess.TimeoutExpired:
                                                    pass
                                                except Exception as e:
                                                    pass
                                            else:
                                                additional_attrs['file_path'] = file_path
                                                additional_attrs['file_size'] = len(file_response.content)
                                                # Usar URL pública acessível
                                                additional_attrs['local_file_url'] = f"/api/media/messages/{conversation.id}/{filename}/"

                                        pass
                                    except requests.Timeout:
                                        pass
                                    except Exception as e:
                                        pass
                            except Exception as e:
                                pass

            except Exception as e:
                pass
        
        # 5. Salvar mensagem recebida - VERIFICAR DUPLICATA
        # Verificar se já existe uma mensagem com o mesmo conteúdo nos últimos 30 segundos
        # Primeiro verificar na mesma conversa
        recent_time = timezone.now() - timedelta(seconds=30)
        existing_message = Message.objects.filter(
            conversation=conversation,
            content=content,
            created_at__gte=recent_time,
            is_from_customer=True
        ).first()
        
        if existing_message:
            content_preview = content[:30] if content else "sem conteúdo"
            return JsonResponse({'status': 'ignored_duplicate'}, status=200)
        
        # Verificar também em outras conversas do mesmo contato (evitar spam)
        existing_message_other_conv = Message.objects.filter(
            conversation__contact=contact,
            content=content,
            created_at__gte=recent_time,
            is_from_customer=True
        ).exclude(conversation=conversation).first()
        
        if existing_message_other_conv:
            content_preview = content[:30] if content else "sem conteúdo"
            return JsonResponse({'status': 'ignored_duplicate'}, status=200)
        
        # Adicionar informações de resposta se for uma mensagem respondida
        if quoted_message and reply_to_content:
            additional_attrs['is_reply'] = True
            additional_attrs['reply_to_message_id'] = reply_to_message_id or quoted_id
            additional_attrs['reply_to_content'] = reply_to_content
            pass
        
        # Determinar o tipo de mensagem para salvar no banco
        db_message_type = message_type if message_type in ['audio', 'image', 'video', 'document', 'sticker', 'ptt', 'media'] else 'incoming'
        
        # Se for mensagem de mídia mas o message_type não for reconhecido, usar o media_type
        if db_message_type == 'incoming' and media_type in ['ptt', 'audio', 'image', 'video', 'document', 'sticker']:
            db_message_type = media_type
        
        # Correção específica para áudio: se message_type é 'media' e media_type é 'ptt', usar 'ptt'
        if message_type == 'media' and media_type == 'ptt':
            db_message_type = 'ptt'
        
        # Correção para áudio detectado pelo mimetype
        if is_audio_message:
            db_message_type = 'audio'
        
        # Correção para imagem: se message_type é 'media' e media_type é 'image', usar 'image'
        if message_type == 'media' and media_type == 'image':
            db_message_type = 'image'
        
        # Correção para vídeo: se message_type é 'media' e media_type é 'video', usar 'video'
        if message_type == 'media' and media_type == 'video':
            db_message_type = 'video'
        
        # Correção para documento: se message_type é 'media' e media_type é 'document', usar 'document'
        if message_type == 'media' and media_type == 'document':
            db_message_type = 'document'
        
        # Extrair dados de mídia dos additional_attrs
        file_url_value = additional_attrs.get('local_file_url') or additional_attrs.get('file_url') or getattr(locals(), 'file_url', None)
        file_name_value = additional_attrs.get('file_name') or getattr(locals(), 'filename', None)
        file_size_value = additional_attrs.get('file_size') or getattr(locals(), 'file_size', None)
        
        msg = Message.objects.create(
            conversation=conversation,
            message_type=db_message_type,
            content=content or '',
            is_from_customer=is_from_customer,  # Usar a variável controlada
            external_id=external_id,  # Salvar external_id no campo correto
            file_url=file_url_value,
            file_name=file_name_value,
            file_size=file_size_value,
            additional_attributes=additional_attrs,
            created_at=timezone.now()
        )
        # PROCESSAR PDFs AUTOMATICAMENTE
        pdf_ja_respondeu = False  # Inicializar variável
        # Garantir que message_id está definido para processamento de PDF
        message_id = external_id or msg_data.get('id') or msg_data.get('key', {}).get('id') or msg_data.get('messageid')
        if db_message_type == 'document' and file_url_value:
            # Verificar se é um PDF - usar msg_data que contém o content original
            is_pdf = False
            
            # Verificar no msg_data que contém o content original
            if isinstance(msg_data, dict) and 'content' in msg_data:
                msg_content = msg_data['content']
                
                if isinstance(msg_content, dict) and msg_content.get('mimetype') == 'application/pdf':
                    is_pdf = True
                elif file_name_value and file_name_value.lower().endswith('.pdf'):
                    is_pdf = True
            
            if is_pdf:
                try:
                    # Importar dependências necessárias
                    from core.openai_service import openai_service
                    from core.pdf_processor import pdf_processor
                    import requests
                    import os
                    
                    # Baixar o PDF usando a API da Uazapi
                    # Usar a API da Uazapi para baixar o arquivo
                    uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
                    uazapi_token = provedor.integracoes_externas.get('whatsapp_token')
                    download_url = f"{uazapi_url}/message/download"
                    download_payload = {
                        'id': message_id,
                        'return_base64': False,
                        'return_link': True,
                    }
                    
                    # Headers com autenticação
                    headers = {
                        'token': uazapi_token,
                        'Content-Type': 'application/json'
                    }
                    
                    response = requests.post(download_url, json=download_payload, headers=headers, timeout=30)
                    if response.status_code == 200:
                        # A API retorna um JSON com fileURL
                        download_result = response.json()
                        
                        if 'fileURL' in download_result:
                            # Baixar o arquivo da URL retornada
                            file_url = download_result['fileURL']
                            
                            file_response = requests.get(file_url, timeout=30)
                            if file_response.status_code == 200:
                                # Salvar temporariamente
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                                    temp_file.write(file_response.content)
                                    temp_pdf_path = temp_file.name
                                
                                # Verificar se o arquivo é realmente um PDF
                                with open(temp_pdf_path, 'rb') as f:
                                    file_content = f.read()
                                    if file_content.startswith(b'%PDF-'):
                                        # Processar PDF com IA
                                        pdf_result = openai_service.process_pdf_with_ai(
                                            pdf_path=temp_pdf_path,
                                            provedor=provedor,
                                            contexto={
                                                'conversation_id': conversation.id,
                                                'contact_name': contact.name,
                                                'file_name': file_name_value
                                            }
                                        )
                                        
                                        # Limpar arquivo temporário
                                        try:
                                            os.unlink(temp_pdf_path)
                                        except:
                                            pass
                                        
                                        # Se o PDF foi processado com sucesso, atualizar o conteúdo para a IA
                                        if pdf_result['success']:
                                            # Atualizar o conteúdo para que a IA processe o conteúdo do PDF
                                            content = pdf_result['resposta']
                                            
                                            # Adicionar informações do PDF ao contexto para a IA
                                            if 'additional_attrs' not in locals():
                                                additional_attrs = {}
                                            additional_attrs['pdf_processed'] = True
                                            additional_attrs['pdf_info'] = pdf_result.get('pdf_info', {})
                                            additional_attrs['file_name'] = file_name_value
                                            
                                            # Atualizar mensagem existente com as informações do PDF
                                            msg.content = content
                                            msg.additional_attributes = additional_attrs
                                            msg.save()
                                            
                                            # Definir a resposta da IA como sendo a resposta do processamento do PDF
                                            resposta_ia = pdf_result['resposta']
                                            ia_result = {
                                                'success': True,
                                                'resposta': pdf_result['resposta'],
                                                'model': 'gpt-4.1',
                                                'provedor': provedor.nome,
                                                'satisfacao_detectada': False
                                            }
                                            
                                            # Marcar que o PDF já foi processado e respondeu para evitar chamada duplicada da IA
                                            pdf_ja_respondeu = True
                                    else:
                                        pdf_result = {
                                            'success': False,
                                            'erro': 'Arquivo não é um PDF válido',
                                            'pdf_info': {'is_payment_receipt': False, 'message': 'Arquivo não é um PDF válido'}
                                        }
                                        
                                        # Limpar arquivo temporário
                                        try:
                                            os.unlink(temp_pdf_path)
                                        except:
                                            pass
                            else:
                                pdf_result = {
                                    'success': False,
                                    'erro': 'Erro ao baixar arquivo',
                                    'pdf_info': {'is_payment_receipt': False, 'message': 'Erro ao baixar o arquivo'}
                                }
                        else:
                            pdf_result = {
                                'success': False,
                                'erro': 'fileURL não encontrado',
                                'pdf_info': {'is_payment_receipt': False, 'message': 'URL do arquivo não encontrada'}
                            }
                    else:
                        pdf_result = {
                            'success': False,
                            'erro': 'Erro na API da Uazapi',
                            'pdf_info': {'is_payment_receipt': False, 'message': 'Erro ao acessar a API'}
                        }
                        
                except Exception as pdf_error:
                    pass
        
        # PROCESSAR IMAGENS AUTOMATICAMENTE
        if db_message_type in ['image', 'media'] and file_url_value:
            # Verificar se é uma imagem usando msg_data original
            is_image = False
            if isinstance(msg_data, dict) and 'content' in msg_data:
                msg_content = msg_data['content']
                if isinstance(msg_content, dict) and msg_content.get('mimetype', '').startswith('image/'):
                    is_image = True
            elif file_name_value and file_name_value.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                is_image = True
            
            if is_image:
                try:
                    # Baixar a imagem usando a API da Uazapi
                    uazapi_url = provedor.integracoes_externas.get('whatsapp_url')
                    download_url = f"{uazapi_url}/message/download"
                    uazapi_token = provedor.integracoes_externas.get('whatsapp_token')
                    download_payload = {
                        'id': message_id,
                        'return_base64': False,
                        'return_link': True,
                    }
                    
                    headers = {
                        'token': uazapi_token,
                        'Content-Type': 'application/json'
                    }
                    
                    response = requests.post(download_url, json=download_payload, headers=headers, timeout=30)
                    if response.status_code == 200:
                        download_result = response.json()
                        
                        if 'fileURL' in download_result:
                            file_url = download_result['fileURL']
                            
                            file_response = requests.get(file_url, timeout=30)
                            if file_response.status_code == 200:
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                                    temp_file.write(file_response.content)
                                    temp_image_path = temp_file.name
                                    
                                # Verificar se o arquivo é realmente uma imagem
                                with open(temp_image_path, 'rb') as f:
                                    file_content = f.read()
                                    
                                    # Verificar se é uma imagem válida (JPEG, PNG, etc.)
                                    if (file_content.startswith(b'\xff\xd8\xff') or  # JPEG
                                        file_content.startswith(b'\x89PNG') or      # PNG
                                        file_content.startswith(b'GIF8') or         # GIF
                                        file_content.startswith(b'RIFF')):          # WEBP
                                        
                                        # Processar imagem com IA
                                        from core.openai_service import openai_service
                                        ai_response = openai_service.analyze_image_with_ai(
                                            image_path=temp_image_path,
                                            provedor=provedor,
                                            contexto={
                                                'conversation_id': conversation.id,
                                                'contact_name': contact.name,
                                                'file_name': file_name_value,
                                                'image_url': file_url
                                            }
                                        )
                                        
                                        if ai_response['success']:
                                            # Verificar se deve transferir para suporte (LED vermelho detectado)
                                            if ai_response.get('transferir_suporte', False):
                                                pass
                                                # Aqui você pode adicionar lógica para transferir para suporte
                                                # Por exemplo, marcar conversa como "precisa de suporte técnico"
                                            
                                            # Enviar resposta da IA sobre a imagem
                                            from integrations.utils import send_whatsapp_message
                                            send_result = send_whatsapp_message(
                                                phone=contact.phone,
                                                message=ai_response['resposta'],
                                                provedor=provedor
                                            )
                                            
                                            if send_result:
                                                Message.objects.create(
                                                    conversation=conversation,
                                                    message_type='outgoing',
                                                    content=ai_response['resposta'],
                                                    is_from_customer=False,
                                                    additional_attributes={
                                                        'auto_response': True,
                                                        'image_analyzed': True,
                                                        'led_vermelho_detectado': ai_response.get('led_vermelho_detectado', False),
                                                        'transferir_suporte': ai_response.get('transferir_suporte', False),
                                                        'file_name': file_name_value
                                                    },
                                                    created_at=timezone.now()
                                                )
                                                
                                                # Imagem processada com sucesso - retornar para evitar processamento adicional pela IA
                                                return JsonResponse({'status': 'image_processed_successfully', 'ai_response_sent': True})
                                            else:
                                                # Mesmo com erro no envio, salvar a resposta da IA no banco
                                                Message.objects.create(
                                                    conversation=conversation,
                                                    message_type='outgoing',
                                                    content=ai_response['resposta'],
                                                    is_from_customer=False,
                                                    additional_attributes={
                                                        'auto_response': True,
                                                        'image_analyzed': True,
                                                        'led_vermelho_detectado': ai_response.get('led_vermelho_detectado', False),
                                                        'transferir_suporte': ai_response.get('transferir_suporte', False),
                                                        'file_name': file_name_value,
                                                        'send_error': True
                                                    },
                                                    created_at=timezone.now()
                                                )
                                                
                                                # Imagem processada com sucesso - retornar para evitar processamento adicional pela IA
                                                return JsonResponse({'status': 'image_processed_successfully', 'ai_response_saved': True, 'send_error': True})
                                    
                                    # Limpar arquivo temporário
                                    try:
                                        os.unlink(temp_image_path)
                                    except:
                                        pass
                except Exception as image_error:
                    pass

        # SALVAR MENSAGEM NO REDIS (UAZAPI WEBHOOK)
        try:
            from core.redis_memory_service import redis_memory_service
            sender_type = 'customer' if is_from_customer else 'agent'
            redis_memory_service.add_message_to_conversation_sync(
                provedor_id=provedor.id,
                conversation_id=conversation.id,
                sender=sender_type,
                content=content or '',
                channel='whatsapp',
                phone=contact.phone,
                message_type=db_message_type
            )
        except Exception as e:
            logger.warning(f"Erro ao salvar mensagem no Redis: {e}")
        
        # Emitir evento WebSocket para a conversa específica
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        from conversations.serializers import MessageSerializer
        message_data = MessageSerializer(msg).data
        
        async_to_sync(channel_layer.group_send)(
            f'conversation_{conversation.id}',
            {
                'type': 'chat_message',
                'message': message_data,
                'sender': None,
                'timestamp': msg.created_at.isoformat(),
            }
        )
        
        # Emitir evento WebSocket para o dashboard
        from conversations.serializers import ConversationSerializer
        async_to_sync(channel_layer.group_send)(
            'conversas_dashboard',
            {
                'type': 'dashboard_event',
                'data': {
                    'action': 'update_conversation',
                    'conversation': ConversationSerializer(conversation).data
                }
            }
        )
        
        # 1. Verificar se é resposta CSAT (só se há CSAT pendente)
        try:
            from conversations.csat_automation import CSATAutomationService
            from conversations.models import CSATRequest
        except ImportError as e:
            logger.warning(f"[UAZAPI] Erro ao importar módulos CSAT: {str(e)}")
            CSATAutomationService = None
            CSATRequest = None
        
        csat_feedback = None
        # Só processar como CSAT se há CSAT pendente para esta conversa
        if CSATRequest and CSATAutomationService:
            csat_pendente = CSATRequest.objects.filter(
                conversation=conversation,
                status='sent'
            ).first()
        else:
            csat_pendente = None
        
        if csat_pendente and content and str(content).strip():
            # Tentar processar como feedback CSAT
            csat_feedback = CSATAutomationService.process_csat_response(
                message_text=str(content),
                conversation=conversation,
                contact=contact
            )
            
            if csat_feedback:
                # Marcar CSAT como processado
                csat_pendente.status = 'completed'
                csat_pendente.save()
                
                # Garantir que conversa permaneça fechada após CSAT
                conversation.status = 'closed'
                conversation.save()
                return JsonResponse({'status': 'csat_processed'})
                
                # CÓDIGO REMOVIDO - estava causando mensagem duplicada
                """
                try:
                    # Gerar resposta personalizada com a IA
                    from core.openai_service import openai_service
                    
                    ia_result = openai_service.generate_response_sync(
                        mensagem=str(content),
                        provedor=provedor,
                        contexto={'conversation': conversation}
                    )
                    
                    if ia_result.get('success'):
                        thanks_text = ia_result.get('resposta')
                        pass
                    else:
                        # Fallback: usar agradecimento padrão
                        thanks_text = "Obrigado pelo seu feedback!"
                    
                    # Enviar agradecimento usando a integração WhatsApp do provedor
                    from integrations.models import WhatsAppIntegration
                    from core.uazapi_client import UazapiClient

                    whatsapp_integration = WhatsAppIntegration.objects.filter(
                        provedor=conversation.inbox.provedor
                    ).first()

                    if whatsapp_integration and contact:
                        base_url = whatsapp_integration.settings.get('whatsapp_url') or whatsapp_integration.webhook_url
                        token = whatsapp_integration.access_token
                        instance = whatsapp_integration.instance_name

                        if base_url and token and instance:
                            client = UazapiClient(base_url, token)
                            # Usar o número do contato diretamente
                            phone = contact.phone
                            if phone:
                                try:
                                    # Limpar o número (remover @s.whatsapp.net se presente)
                                    clean_phone = phone.replace('@s.whatsapp.net', '').replace('@c.us', '')
                                    
                                    # Usar método correto do UazapiClient
                                    result = client.enviar_mensagem(
                                        numero=clean_phone, 
                                        texto=thanks_text,
                                        instance_id=instance
                                    )
                                except Exception as e:
                                    pass
                except Exception:
                    pass
                return JsonResponse({'success': True, 'csat_processed': True, 'rating': csat_feedback.emoji_rating})
                """
        
        # Se não foi processado como CSAT, continuar fluxo normal da IA
        
        # 2.a Se for áudio, tentar baixar/transcrever via Uazapi e anexar ao conteúdo para IA
        try:
            if db_message_type in ['audio', 'ptt'] and 'id' in msg_data:
                audio_msg_id = (msg_data.get('id') or msg_data.get('messageId') or msg_data.get('messageid') or msg_data.get('key', {}).get('id'))
                if audio_msg_id:
                    from core.uazapi_client import UazapiClient
                    client = UazapiClient(uazapi_url, uazapi_token)
                    
                    # CONFIGURAÇÕES DINÂMICAS DE TRANSCRIÇÃO POR PROVEDOR
                    transcription_config = provedor.integracoes_externas.get('transcription_config', {})
                    language = transcription_config.get('language', 'pt-BR')
                    quality = transcription_config.get('quality', 'high')
                    delay_between = transcription_config.get('delay_between', 1)
                    enable_double = transcription_config.get('enable_double_transcription', True)
                    
                    # Usar chave OpenAI EXCLUSIVA para transcrição de áudio
                    # Esta chave NÃO é usada para geração de respostas (que usa Gemini)
                    from core.models import SystemConfig
                    # IMPORTANTE: Buscar pela mesma key que a view usa ('system_config')
                    # Isso garante que estamos pegando a mesma instância que foi salva
                    cfg = SystemConfig.objects.filter(key='system_config').first()
                    
                    # Se não encontrar com key='system_config', tentar qualquer uma (fallback)
                    if not cfg:
                        cfg = SystemConfig.objects.first()
                    
                    openai_key = None
                    if cfg:
                        # Forçar refresh do banco para evitar cache do ORM
                        cfg.refresh_from_db()
                        if cfg.openai_transcription_api_key:
                            openai_key = cfg.openai_transcription_api_key.strip() if cfg.openai_transcription_api_key else None
                            # Validar se a chave não está vazia e tem tamanho mínimo
                            if openai_key and len(openai_key) >= 20:
                                logger.info(f"[EVOLUTION] ✓ Chave OpenAI para transcrição configurada (tamanho: {len(openai_key)} caracteres)")
                            elif openai_key:
                                logger.error(f"[EVOLUTION] ✗ Chave OpenAI muito curta ou inválida (tamanho: {len(openai_key)} caracteres)")
                                openai_key = None
                            else:
                                logger.warning(f"[EVOLUTION] ✗ Campo openai_transcription_api_key está vazio no SystemConfig")
                        else:
                            logger.warning(f"[EVOLUTION] ✗ Campo openai_transcription_api_key não configurado no SystemConfig")
                    else:
                        logger.warning(f"[EVOLUTION] ✗ SystemConfig não encontrado")
                    
                    if not openai_key:
                        logger.warning(f"[EVOLUTION] ✗ Chave de API OpenAI não disponível, não será possível transcrever o áudio. Configure openai_transcription_api_key no painel do superadmin.")
                    
                    # PRIMEIRA TRANSCRIÇÃO
                    dl1 = client.download_message(
                        message_id=audio_msg_id,
                        generate_mp3=True,
                        return_base64=False,
                        return_link=True,
                        transcribe=True,
                        openai_apikey=openai_key
                    )
                    transcription1 = dl1.get('transcription') if isinstance(dl1, dict) else None
                    
                    # Delay dinâmico entre transcrições
                    if enable_double:
                        import time
                        time.sleep(delay_between)
                        
                        # SEGUNDA TRANSCRIÇÃO (para garantir precisão)
                        dl2 = client.download_message(
                            message_id=audio_msg_id,
                            generate_mp3=True,
                            return_base64=False,
                            return_link=True,
                            transcribe=True,
                            openai_apikey=openai_key
                        )
                        transcription2 = dl2.get('transcription') if isinstance(dl2, dict) else None
                        
                        # COMPARAR TRANSCRIÇÕES E ESCOLHER A MELHOR
                        final_transcription = None
                        if transcription1 and transcription2:
                            # Se as transcrições são idênticas, usar qualquer uma
                            if transcription1.strip().lower() == transcription2.strip().lower():
                                final_transcription = transcription1
                            else:
                                # Se diferentes, usar a mais longa (geralmente mais precisa)
                                if len(transcription1) > len(transcription2):
                                    final_transcription = transcription1
                                else:
                                    final_transcription = transcription2
                        elif transcription1:
                            final_transcription = transcription1
                        elif transcription2:
                            final_transcription = transcription2
                    else:
                        # TRANSCRIÇÃO ÚNICA (quando dupla está desabilitada)
                        final_transcription = transcription1
                    
                    if final_transcription:
                        additional_attrs['transcription'] = final_transcription
                        additional_attrs['transcription1'] = transcription1
                        additional_attrs['transcription2'] = transcription2 if enable_double else None
                        additional_attrs['transcription_config'] = {
                            'language': language,
                            'quality': quality,
                            'delay_between': delay_between,
                            'enable_double': enable_double,
                            'provedor': provedor.nome
                        }
                        # Usar a transcrição final como conteúdo para IA
                        content = final_transcription
        except Exception as e:
            logger.warning(f"[UAZAPI] Erro ao processar transcrição de áudio para conversa {conversation.id}: {str(e)}")

        # 2. Acionar IA para resposta automática (apenas se não foi CSAT e não estiver atribuída)
        
        # Inicializar variáveis
        ia_result = None
        resposta_ia = None
        
        # Verificar se o PDF já foi processado e respondeu para evitar chamada duplicada da IA
        if pdf_ja_respondeu:
            # A resposta já foi definida no processamento do PDF, não fazer nada aqui
            # resposta_ia já deve ter sido definida no processamento do PDF, mas verificar se não está None
            if not resposta_ia:
                # Se resposta_ia não foi definida no processamento do PDF, usar o conteúdo
                resposta_ia = content if content else None
        elif content and str(content).strip():  # Verificar se há conteúdo válido antes de chamar a IA
            # Importar openai_service
            from core.openai_service import openai_service
            
            # Verificar se o contato está bloqueado para atendimento
            # Se bloqueado_atender = True, a IA NÃO deve responder
            if contact and contact.bloqueado_atender:
                logger.warning(f"[UAZAPI] IA NÃO chamada - contato {contact.phone} ({contact.name}) está BLOQUEADO para atendimento (bloqueado_atender=True)")
                ia_result = {
                    'success': False,
                    'motivo': 'Contato bloqueado para atendimento',
                    'bloqueado': True
                }
            # Verificar se conversa está atribuída ou em espera
            # Permitir resposta da IA se não estiver atribuída e não estiver fechada
            elif conversation.assignee is None and conversation.status not in ['closed', 'resolved']:
                # Verificar se a IA está ativa no canal
                from core.models import Canal
                canal = None
                # Tentar buscar canal pelo channel_id do inbox
                if conversation.inbox.channel_id and conversation.inbox.channel_id != 'default':
                    try:
                        canal = Canal.objects.filter(
                            id=conversation.inbox.channel_id,
                            provedor=provedor
                        ).first()
                    except (ValueError, TypeError):
                        pass
                
                # Se não encontrou pelo channel_id, buscar pelo tipo do canal
                if not canal:
                    channel_type = conversation.inbox.channel_type
                    if channel_type == 'whatsapp':
                        # Para WhatsApp normal, buscar por nome da instância se disponível
                        instance_name = conversation.inbox.additional_attributes.get('instance') if conversation.inbox.additional_attributes else None
                        if instance_name:
                            canal = Canal.objects.filter(
                                provedor=provedor,
                                nome=instance_name,
                                tipo__in=['whatsapp', 'whatsapp_session'],
                                ativo=True
                            ).first()
                
                # Se encontrou o canal e a IA está desativada, não chamar IA
                if canal and not canal.ia_ativa:
                    logger.info(f"[UAZAPI] IA NÃO chamada - canal {canal.id} ({canal.nome}) tem IA desativada (ia_ativa=False)")
                    ia_result = {
                        'success': False,
                        'motivo': 'IA desativada no canal',
                        'ia_desativada': True
                    }
                else:
                    try:
                        ia_result = openai_service.generate_response_sync(
                            mensagem=str(content),  # Garantir que é string
                            provedor=provedor,
                            contexto={'conversation': conversation}
                        )
                        
                        # IMPORTANTE: Se a conversa está em 'pending', não alterar status nem atribuição
                        # A IA pode responder, mas a conversa continua aguardando atendente/equipe
                        if conversation.status != 'pending':
                            # Verificar se a IA detectou interesse comercial e atualizar status de recuperação
                            # Apenas se NÃO estiver em pending
                            if ia_result.get('success') and 'TRANSFERÊNCIA DETECTADA: VENDAS' in str(ia_result):
                                from conversations.recovery_service import ConversationRecoveryService
                                recovery_service = ConversationRecoveryService()
                                recovery_service.update_recovery_status_from_conversation(conversation.id, str(content))
                    except Exception as e:
                        ia_result = {'success': False, 'erro': str(e)}
            else:
                ia_result = {'success': False, 'motivo': 'Conversa atribuída ou em espera'}
        else:
            logger.warning(f"[UAZAPI] IA não chamada - mensagem sem conteúdo válido para conversa {conversation.id}")
            ia_result = {'success': False, 'erro': 'Mensagem sem conteúdo válido'}
        
        # Definir resposta_ia baseada no processamento do PDF ou da IA
        if pdf_ja_respondeu:
            # Se o PDF foi processado, usar a resposta do PDF que já foi definida
            if resposta_ia:
                # resposta_ia já foi definida no processamento do PDF
                pass
            elif ia_result and ia_result.get('success'):
                resposta_ia = ia_result.get('resposta')
            else:
                # Usar o conteúdo que foi processado pelo PDF
                resposta_ia = content if content else None
        else:
            # Se não foi PDF, usar a resposta da IA
            if ia_result and ia_result.get('success'):
                resposta_ia = ia_result.get('resposta')
            else:
                resposta_ia = None
                if ia_result:
                    erro_ia = ia_result.get('erro') or ia_result.get('motivo')
                    logger.warning(f"[UAZAPI] IA não retornou resposta válida para conversa {conversation.id}: {erro_ia}")
                    
                    # Se o erro for de pacote não instalado (google-genai)
                    if 'google-genai' in str(erro_ia).lower() or 'nova API do Google' in str(erro_ia):
                        logger.error(f"[UAZAPI] Pacote google-genai não instalado - {erro_ia}. Execute: pip install google-genai")
                else:
                    logger.warning(f"[UAZAPI] ia_result não definido para conversa {conversation.id}")
        
        # 🚨 SEGURANÇA CRÍTICA: Remover qualquer código antes de enviar ao cliente
        if resposta_ia:
            from core.ai_response_formatter import AIResponseFormatter
            formatter = AIResponseFormatter()
            resposta_ia = formatter.remover_exposicao_funcoes(resposta_ia)
        
        # 🚨 CORREÇÃO: WhatsApp usa *texto* (UM asterisco), não **texto** (dois asteriscos)
        # Limpar formatação incorreta se for WhatsApp
        if resposta_ia:
            import re
            # Substituir **texto** por *texto* (manter apenas um asterisco)
            resposta_ia = re.sub(r'\*\*([^*]+?)\*\*', r'*\1*', resposta_ia)
        
        # 3. Enviar resposta para Uazapi (WhatsApp)
        import requests
        send_result = None
        success = False
        if resposta_ia and uazapi_token and uazapi_url:
            # Usar APENAS chatid para envio da resposta da IA
            destination_number = chatid_full
            if destination_number:
                try:
                    # Limpar o número (remover @s.whatsapp.net se presente)
                    clean_number = destination_number.replace('@s.whatsapp.net', '').replace('@c.us', '')
                    
                    # 🚨 REGRA DE OURO #1: VALIDAÇÃO OBRIGATÓRIA DE QUEBRAS DE LINHA
                    def validar_quebras_linha(texto):
                        """Valida e corrige quebras de linha antes de enviar"""
                        # Converter \n literal para quebra de linha real
                        texto = texto.replace('\\n', '\n')
                        # Garantir que quebras de linha duplas sejam preservadas
                        texto = texto.replace('\n\n', '\n\n')
                        return texto
                    
                    # 🚨 REGRA DE OURO: Detectar confirmação de dados do contrato e separar mensagens
                    if 'CONFIRMAÇÃO DE DADOS DO CONTRATO' in resposta_ia and 'Essas informações estão corretas?' in resposta_ia:
                        # Separar a mensagem em duas partes
                        partes = resposta_ia.split('Essas informações estão corretas?')
                        dados_confirmacao = partes[0].strip()
                        pergunta = 'Essas informações estão corretas?'
                        
                        # PASSO 1: VALIDAR QUEBRAS DE LINHA
                        dados_confirmacao = validar_quebras_linha(dados_confirmacao)
                        
                        # PASSO 2: TODA MENSAGEM DEVE TER DELAY (1000ms padrão)
                        payload_dados = {
                            'number': clean_number,
                            'delay': 1000,
                            'text': dados_confirmacao
                        }
                        send_resp_dados = requests.post(
                            f"{uazapi_url.rstrip('/')}/send/text",
                            headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                            json=payload_dados,
                            timeout=10
                        )
                        
                        if send_resp_dados.status_code == 200:
                            # Aguardar 1 segundo antes de enviar a pergunta
                            import time
                            time.sleep(1)
                            
                            # PASSO 2: TODA MENSAGEM DEVE TER DELAY (1000ms padrão)
                            payload_pergunta = {
                                'number': clean_number,
                                'delay': 1000,
                                'text': pergunta
                            }
                            send_resp_pergunta = requests.post(
                                f"{uazapi_url.rstrip('/')}/send/text",
                                headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                                json=payload_pergunta,
                                timeout=10
                            )
                            if send_resp_pergunta.status_code == 200:
                                send_result = send_resp_pergunta.json() if send_resp_pergunta.content else send_resp_pergunta.status_code
                                success = True
                            else:
                                pass
                        else:
                            pass
                    else:
                        # Mensagem normal - enviar normalmente
                        # PASSO 1: VALIDAR QUEBRAS DE LINHA
                        resposta_formatada = validar_quebras_linha(resposta_ia)
                        
                        # PASSO 2: TODA MENSAGEM DE TEXTO DA IA DEVE TER DELAY (1000ms padrão)
                        payload = {
                            'number': clean_number,
                            'delay': 1000,
                            'text': resposta_formatada
                        }
                        send_resp = requests.post(
                            f"{uazapi_url.rstrip('/')}/send/text",
                            headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                            json=payload,
                            timeout=10
                        )
                        if send_resp.status_code == 200:
                            send_result = send_resp.json() if send_resp.content else send_resp.status_code
                            success = True
                        else:
                            pass
                except Exception as e:
                    logger.error(f"[UAZAPI] Erro ao enviar mensagem: {e}")
                    pass
            else:
                logger.warning(f"[UAZAPI] destination_number não definido para conversa {conversation.id}")
        else:
            if not resposta_ia:
                logger.warning(f"[UAZAPI] resposta_ia não definida para conversa {conversation.id}")
            if not uazapi_token:
                logger.warning(f"[UAZAPI] uazapi_token não definido para conversa {conversation.id}")
            if not uazapi_url:
                logger.warning(f"[UAZAPI] uazapi_url não definido para conversa {conversation.id}")
        
        # CORREÇÃO: Salvar mensagem da IA SEMPRE que houver resposta, independente do sucesso do envio
        # A mensagem deve aparecer no chat mesmo se o envio para WhatsApp falhar
        if resposta_ia:
            # Verificar se já existe uma mensagem da IA com o mesmo conteúdo nos últimos 30 segundos
            recent_time = timezone.now() - timedelta(seconds=30)
            existing_ia_message = Message.objects.filter(
                conversation=conversation,
                content=resposta_ia,
                created_at__gte=recent_time,
                is_from_customer=False
            ).first()
            
            if existing_ia_message:
                resposta_preview = str(resposta_ia)[:30] if resposta_ia else "sem resposta"
            else:
                # Verificar se a conversa ainda existe no PostgreSQL local (pode ter sido migrada)
                try:
                    ConversationModel.objects.get(id=conversation.id)
                except ConversationModel.DoesNotExist:
                    # Conversa foi migrada para Supabase, não criar mensagem no local
                    logger.warning(f"Conversa {conversation.id} não encontrada localmente (já migrada). Pulando criação de mensagem da IA.")
                    resposta_preview = str(resposta_ia)[:30] if resposta_ia else "sem resposta"
                else:
                    ia_additional_attrs = {'from_ai': True}
                    
                    msg_ia = Message.objects.create(
                        conversation=conversation,
                        message_type='text',  # CORREÇÃO: Usar tipo válido do modelo
                        content=resposta_ia,
                        is_from_customer=False,
                        additional_attributes=ia_additional_attrs,  # Marcar como mensagem da IA
                        created_at=timezone.now()
                    )
                    
                    resposta_preview = str(resposta_ia)[:30] if resposta_ia else "sem resposta"
                    
                    # SALVAR MENSAGEM DA IA NO REDIS (UAZAPI WEBHOOK)
                    try:
                        from core.redis_memory_service import redis_memory_service
                        redis_memory_service.add_message_to_conversation_sync(
                            provedor_id=provedor.id,
                            conversation_id=conversation.id,
                            sender='ai',
                            content=resposta_ia,
                            channel='whatsapp',
                            phone=contact.phone,
                            message_type='text'
                        )
                    except Exception as e:
                        logger.warning(f"Erro ao salvar mensagem da IA no Redis: {e}")
                    
                    # CORREÇÃO: Emitir evento WebSocket para mensagem da IA (UAZAPI)
                    # Garantir que o sender seja 'ai' para identificar corretamente
                    async_to_sync(channel_layer.group_send)(
                        f'conversation_{conversation.id}',
                        {
                            'type': 'chat_message',
                            'message': MessageSerializer(msg_ia).data,
                            'sender': 'ai',  # CORREÇÃO: Identificar como mensagem da IA
                            'timestamp': msg_ia.created_at.isoformat(),
                        }
                    )
        # Retornar 'ok' se a mensagem foi processada, independente do sucesso da resposta da IA
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'error': str(e), 'traceback': traceback.format_exc()}, status=500)
class LoginView(APIView):
    """Endpoint customizado para login - cria token e audit log"""
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        from rest_framework.authtoken.models import Token
        from django.contrib.auth import authenticate
        from core.asaas_provedor_block import is_asaas_auto_inadimplencia_reason
        
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({'error': 'Username e password são obrigatórios'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Autenticar usuário
        user = authenticate(username=username, password=password)
        
        if not user:
            logger.warning(f"Falha de login: credenciais inválidas para username={username}")
            return Response({'error': 'Credenciais inválidas'}, status=status.HTTP_401_UNAUTHORIZED)

        # Bloqueio de acesso para suspensão MANUAL do provedor (superadmin)
        # Regra: se o provedor está inativo por motivo NÃO financeiro automático, bloquear no login.
        if getattr(user, 'user_type', None) != 'superadmin':
            try:
                provedores_usuario = []
                if hasattr(user, 'provedor') and user.provedor:
                    provedores_usuario.append(user.provedor)
                if hasattr(user, 'provedores_admin'):
                    for p in user.provedores_admin.all():
                        if p and p not in provedores_usuario:
                            provedores_usuario.append(p)

                for provedor_user in provedores_usuario:
                    if provedor_user and provedor_user.is_active is False:
                        reason = (provedor_user.block_reason or '').strip()
                        is_financial_block = is_asaas_auto_inadimplencia_reason(reason)
                        if not is_financial_block:
                            return Response(
                                {'error': 'Acesso não autorizado. Provedor suspenso pelo administrador do sistema.'},
                                status=status.HTTP_403_FORBIDDEN
                            )
            except Exception as block_check_err:
                logger.warning(f"Falha ao validar suspensão manual no login: {block_check_err}")
        
        # Obter ou criar token para o usuário
        from django.db import transaction
        with transaction.atomic():
            token, created = Token.objects.get_or_create(user=user)
            token.refresh_from_db()
        
        # Obter provedor_id do usuário
        provedor_id = None
        if hasattr(user, 'provedor_id') and user.provedor_id:
            provedor_id = user.provedor_id
        elif hasattr(user, 'provedor') and user.provedor:
            provedor_id = user.provedor.id
        elif hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
            provedor_id = user.provedores_admin.first().id
        
        # Criar audit log de login
        if provedor_id:
            try:
                provedor = Provedor.objects.get(id=provedor_id)
                AuditLog.objects.create(
                    user=user,
                    action='login',
                    details=f"Login bem-sucedido - Usuário: {user.username}",
                    provedor=provedor,
                    timestamp=timezone.now()
                )
            except Provedor.DoesNotExist:
                pass
            except Exception as e:
                logger.warning(f'Erro ao criar audit log de login: {e}')
        
        # Retornar token garantindo que está commitado
        return Response({'token': token.key}, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Endpoint para logout - invalida o token do usuário e cria audit log"""
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        try:
            user = request.user
            
            # Obter provedor_id do usuário antes de deletar o token
            provedor_id = None
            if hasattr(user, 'provedor_id') and user.provedor_id:
                provedor_id = user.provedor_id
            elif hasattr(user, 'provedor') and user.provedor:
                provedor_id = user.provedor.id
            elif hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                provedor_id = user.provedores_admin.first().id
            
            # Deletar o token do usuário usando Token.objects
            from rest_framework.authtoken.models import Token
            try:
                token = Token.objects.get(user=user)
                token.delete()
                logger.info(f'Token deletado para usuário {user.id}')
            except Token.DoesNotExist:
                # Token já não existe, considerar logout bem-sucedido
                logger.info(f'Token já não existe para usuário {user.id}')
            
            # Criar audit log de logout
            if provedor_id:
                try:
                    provedor = Provedor.objects.get(id=provedor_id)
                    AuditLog.objects.create(
                        user=user,
                        action='logout',
                        details=f"Logout realizado - Usuário: {user.username}",
                        provedor=provedor,
                        timestamp=timezone.now()
                    )
                except Provedor.DoesNotExist:
                    pass
            
            return Response({'success': True, 'message': 'Logout realizado com sucesso'}, status=status.HTTP_200_OK)
        except Exception as e:
            # Se houver erro, ainda retornar sucesso (não bloquear o logout)
            logger.warning(f'Erro ao deletar token no logout: {e}')
            return Response({'success': True, 'message': 'Logout realizado com sucesso'}, status=status.HTTP_200_OK)


class RefreshTokenView(APIView):
    """Endpoint para refresh token - retorna token atual ou regenera se necessário"""
    authentication_classes = [LoggedTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        from rest_framework.authtoken.models import Token
        
        # Log do header de autorização recebido
        auth_header = request.headers.get('Authorization', 'N/A')
        logger.info(f"[REFRESH] Request recebido - Header: {auth_header[:30]}...")
        
        try:
            user = request.user
            logger.info(f"[REFRESH] Usuário autenticado: user_id={user.id}, username={user.username}")
            
            # Obter ou criar token (se não existir, cria novo)
            token, created = Token.objects.get_or_create(user=user)
            
            # Garantir que o token está atualizado no banco
            token.refresh_from_db()
            
            # Verificar se o token existe no banco
            try:
                Token.objects.get(key=token.key, user=user)
                logger.info(f"[REFRESH] Token confirmado no banco: user_id={user.id}, token_key={token.key[:20]}..., created={created}")
            except Token.DoesNotExist:
                logger.error(f"[REFRESH] ERRO: Token criado mas não encontrado no banco! user_id={user.id}")
            
            return Response({'token': token.key}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"[REFRESH] Erro ao processar refresh: {e}", exc_info=True)
            logger.warning(f"[REFRESH] Header recebido: {auth_header[:30]}...")
            return Response({'error': 'Erro ao processar refresh'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserMeView(APIView):
    authentication_classes = [LoggedTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        try:
            user = request.user
            # Verificar se o usuário está autenticado
            if not user or not user.is_authenticated:
                return Response({'error': 'Usuário não autenticado'}, status=401)
            
            # Obter provedor_id do primeiro provedor associado ao usuário
            provedor_id = None
            try:
                if hasattr(user, 'provedores_admin'):
                    provedores = user.provedores_admin.all()
                    if provedores.exists():
                        provedor = provedores.first()
                        provedor_id = provedor.id if provedor else None
                else:
                    logger.warning(f"Usuário {user.id} não possui provedores_admin")
            except Exception as e:
                logger.warning(f"Erro ao buscar provedor do usuário {user.id}: {e}")
                provedor_id = None
            
            # Obter avatar URL se existir
            avatar_url = None
            try:
                if hasattr(user, 'avatar') and user.avatar:
                    avatar_url = user.avatar.url if hasattr(user.avatar, 'url') else str(user.avatar)
            except Exception:
                avatar_url = None
            
            # Obter lista de IDs dos provedores do usuário
            provedores_admin_ids = []
            try:
                if hasattr(user, 'provedores_admin'):
                    provedores_admin_ids = list(user.provedores_admin.values_list('id', flat=True))
            except Exception:
                pass
            
            # Montar resposta com dados do usuário
            response_data = {
                'id': user.id,
                'username': getattr(user, 'username', ''),
                'email': getattr(user, 'email', ''),
                'first_name': getattr(user, 'first_name', ''),
                'last_name': getattr(user, 'last_name', ''),
                'user_type': getattr(user, 'user_type', ''),
                # Compatibilidade com partes do frontend que ainda usam "role"
                'role': getattr(user, 'user_type', ''),
                'permissions': getattr(user, 'permissions', []) if isinstance(getattr(user, 'permissions', []), list) else [],
                'is_staff': getattr(user, 'is_staff', False),
                'is_superuser': getattr(user, 'is_superuser', False),
                'provedor_id': provedor_id,
                'provedores_admin': provedores_admin_ids,  # Adicionar lista de IDs dos provedores
                'avatar': avatar_url,
                'phone': getattr(user, 'phone', ''),
                'is_online': getattr(user, 'is_online', False),
            }
            
            # Adicionar language se existir
            try:
                if hasattr(user, 'language'):
                    response_data['language'] = getattr(user, 'language', 'pt')
            except Exception:
                response_data['language'] = 'pt'
            
            # Adicionar session_timeout se existir
            try:
                if hasattr(user, 'session_timeout'):
                    response_data['session_timeout'] = getattr(user, 'session_timeout', 30)
            except Exception:
                response_data['session_timeout'] = 30
            
            # Adicionar campos de som se existirem
            try:
                if hasattr(user, 'sound_notifications_enabled'):
                    response_data['sound_notifications_enabled'] = getattr(user, 'sound_notifications_enabled', False)
                if hasattr(user, 'new_message_sound'):
                    response_data['new_message_sound'] = getattr(user, 'new_message_sound', '01.mp3')
                if hasattr(user, 'new_message_sound_volume'):
                    response_data['new_message_sound_volume'] = getattr(user, 'new_message_sound_volume', 1.0)
                if hasattr(user, 'new_conversation_sound'):
                    response_data['new_conversation_sound'] = getattr(user, 'new_conversation_sound', '02.mp3')
                if hasattr(user, 'new_conversation_sound_volume'):
                    response_data['new_conversation_sound_volume'] = getattr(user, 'new_conversation_sound_volume', 1.0)
            except Exception:
                pass
            
            # Adicionar campo assignment_message se existir
            try:
                if hasattr(user, 'assignment_message'):
                    response_data['assignment_message'] = getattr(user, 'assignment_message', '') or ''
            except Exception:
                response_data['assignment_message'] = ''
            
            return Response(response_data)
        except Exception as e:
            logger.error(f"Erro em UserMeView: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)
    
    def patch(self, request):
        """
        Atualiza dados do usuário logado
        """
        try:
            user = request.user
            
            # Verificar se o usuário está autenticado
            if not user or not user.is_authenticated:
                return Response({'error': 'Usuário não autenticado'}, status=401)
            
            # Atualizar campos permitidos
            updated_fields = []
            
            if 'first_name' in request.data:
                user.first_name = request.data['first_name']
                updated_fields.append('first_name')
            
            if 'last_name' in request.data:
                user.last_name = request.data['last_name']
                updated_fields.append('last_name')
            
            if 'email' in request.data:
                user.email = request.data['email']
                updated_fields.append('email')
            
            if 'phone' in request.data:
                user.phone = request.data.get('phone', '') or ''
                updated_fields.append('phone')
            
            if 'language' in request.data:
                user.language = request.data['language']
                updated_fields.append('language')
            
            if 'session_timeout' in request.data:
                user.session_timeout = request.data['session_timeout']
                updated_fields.append('session_timeout')
            
            if 'assignment_message' in request.data:
                user.assignment_message = request.data['assignment_message']
                updated_fields.append('assignment_message')
            
            if 'sound_notifications_enabled' in request.data:
                user.sound_notifications_enabled = request.data['sound_notifications_enabled']
                updated_fields.append('sound_notifications_enabled')
            
            if 'new_message_sound' in request.data:
                user.new_message_sound = request.data.get('new_message_sound', '')
                updated_fields.append('new_message_sound')
            
            if 'new_message_sound_volume' in request.data:
                user.new_message_sound_volume = float(request.data.get('new_message_sound_volume', 1.0))
                updated_fields.append('new_message_sound_volume')
            
            if 'new_conversation_sound' in request.data:
                user.new_conversation_sound = request.data.get('new_conversation_sound', '')
                updated_fields.append('new_conversation_sound')

            if 'new_conversation_sound_volume' in request.data:
                user.new_conversation_sound_volume = float(request.data.get('new_conversation_sound_volume', 1.0))
                updated_fields.append('new_conversation_sound_volume')
            
            # Salvar apenas se houver campos para atualizar
            if updated_fields:
                user.save(update_fields=updated_fields)
                logger.info(f"Perfil do usuário {user.id} atualizado. Campos: {', '.join(updated_fields)}")
            
            # Retornar dados atualizados
            return self.get(request)
            
        except Exception as e:
            logger.error(f"Erro ao atualizar perfil em UserMeView: {e}", exc_info=True)
            return Response({'error': f'Erro ao atualizar perfil: {str(e)}'}, status=500)

class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar usuários
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer
    
    def get_queryset(self):
        user = self.request.user
        
        # Superadmin vê todos os usuários
        if user.user_type == 'superadmin':
            queryset = User.objects.all()
        else:
            # Outros usuários veem apenas usuários do mesmo provedor (ISOLAMENTO POR PROVEDOR)
            # Usar o mesmo padrão dos outros ViewSets: user.provedores_admin.all()
            provedores = user.provedores_admin.all()
            if provedores.exists():
                # Filtrar apenas usuários que pertencem aos mesmos provedores do usuário atual
                queryset = User.objects.filter(
                    provedores_admin__in=provedores
                ).distinct()
            else:
                queryset = User.objects.none()
        
        # Filtrar por provedor se fornecido (ISOLAMENTO ADICIONAL)
        provedor_param = self.request.query_params.get('provedor')
        if provedor_param:
            if provedor_param == 'me':
                # Filtrar pelo provedor do usuário atual
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                    queryset = queryset.filter(provedores_admin=provedor)
            else:
                try:
                    provedor_id = int(provedor_param)
                    # Filtrar apenas usuários do provedor especificado (ISOLAMENTO)
                    queryset = queryset.filter(provedores_admin__id=provedor_id)
                except (ValueError, TypeError):
                    pass
        
        # Filtrar por status se fornecido
        include_status = self.request.query_params.get('include_status')
        if include_status == 'true':
            # Incluir informações de status online
            queryset = queryset.select_related()
        
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        user = self.request.user
        # Verificar permissões
        if user.user_type not in ['superadmin', 'admin']:
            raise PermissionDenied('Apenas administradores podem criar usuários')
        
        # Definir provedor se não fornecido
        if 'provedor_id' in serializer.validated_data:
            provedor_id = serializer.validated_data['provedor_id']
            provedor = Provedor.objects.filter(id=provedor_id).first()
            if provedor:
                user_obj = serializer.save()
                user_obj.provedores_admin.add(provedor)
            else:
                serializer.save()
        else:
            serializer.save()
    
    def perform_update(self, serializer):
        user = self.request.user
        
        # Verificar permissões
        if user.user_type not in ['superadmin', 'admin']:
            # Agentes só podem atualizar a si mesmos
            if serializer.instance.id != user.id:
                raise PermissionDenied('Você não tem permissão para atualizar este usuário')
            # Agente não pode elevar função/permissões nem alterar status/acesso
            blocked_fields = {'user_type', 'permissions', 'is_active', 'write_provedor_id', 'provedor_id'}
            if any(field in self.request.data for field in blocked_fields):
                raise PermissionDenied('Você não tem permissão para alterar função/permissões deste usuário')
        
        serializer.save()
    
    def perform_destroy(self, instance):
        user = self.request.user
        # Verificar permissões
        if user.user_type not in ['superadmin', 'admin']:
            raise PermissionDenied('Apenas administradores podem deletar usuários')
        
        # Invalidar token antes de excluir para deslogar sessões ativas imediatamente
        from rest_framework.authtoken.models import Token
        try:
            Token.objects.filter(user=instance).delete()
        except Exception:
            pass
        
        instance.delete()

    @action(detail=False, methods=['post'], url_path='reset-password')
    def reset_password(self, request):
        """
        Altera a senha do usuário autenticado.
        POST body: { "new_password": "..." }
        """
        user = request.user
        new_password = request.data.get('new_password')
        if not new_password or not isinstance(new_password, str):
            return Response(
                {'error': 'new_password é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )
        new_password = new_password.strip()
        if len(new_password) < 6:
            return Response(
                {'error': 'A senha deve ter pelo menos 6 caracteres'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            from django.contrib.auth.password_validation import validate_password
            validate_password(new_password, user=user)
        except Exception as e:
            err = getattr(e, 'messages', [str(e)])
            msg = err[0] if err else 'Senha não atende aos critérios de segurança'
            return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({'detail': 'Senha alterada com sucesso'}, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['get'], url_path='my_provider_users')
    def my_provider_users(self, request):
        """
        Lista usuários do mesmo provedor para chat privado
        Funciona para todos os tipos de usuário (admin, agent, superadmin)
        """
        user = request.user
        
        try:
            import logging
            logger = logging.getLogger(__name__)
            
            # Buscar provedor do usuário logado
            provedor = None
            
            # Método 1: Buscar através de provedores_admin (ManyToManyField)
            # Isso funciona para usuários que são admins de um provedor
            if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                provedor = user.provedores_admin.first()
                logger.info(f"[MY_PROVIDER_USERS] Provedor encontrado via provedores_admin: {provedor.id if provedor else None}")
            
            # Método 2: Se não encontrou, buscar através da relação reversa
            # Isso também funciona para usuários que são admins
            if not provedor:
                provedores = Provedor.objects.filter(admins=user)
                if provedores.exists():
                    provedor = provedores.first()
                    logger.info(f"[MY_PROVIDER_USERS] Provedor encontrado via filter(admins): {provedor.id if provedor else None}")
            
            # Verificar parâmetro para incluir o próprio usuário (útil para gestão de equipes)
            include_self = request.query_params.get('include_self', 'false').lower() == 'true'
            
            if provedor:
                # Buscar TODOS os usuários do mesmo provedor
                users_query = User.objects.filter(
                    provedores_admin=provedor
                ).filter(is_active=True).distinct()
                
                if not include_self:
                    users_query = users_query.exclude(id=user.id)
                
                users = users_query
                logger.info(f"[MY_PROVIDER_USERS] Usuários encontrados: {users.count()} para provedor {provedor.id} (include_self={include_self})")
            else:
                # Se não encontrou provedor, verificar se é superadmin
                if user.user_type == 'superadmin':
                    # Superadmin pode ver todos os usuários ativos
                    users_query = User.objects.filter(is_active=True)
                    if not include_self:
                        users_query = users_query.exclude(id=user.id)
                    users = users_query
                    logger.info(f"[MY_PROVIDER_USERS] Superadmin - Usuários encontrados: {users.count()} (include_self={include_self})")
                else:
                    # Usuário sem provedor não pode ver ninguém
                    users = User.objects.none()
                    logger.warning(f"[MY_PROVIDER_USERS] Usuário {user.id} sem provedor - retornando lista vazia")
            
            # Serializar dados básicos
            users_data = []
            for u in users:
                user_data = {
                    'id': u.id,
                    'username': u.username,
                    'first_name': u.first_name or '',
                    'last_name': u.last_name or '',
                    'avatar': None,  # Simplificado - sem avatar por enquanto
                    'user_type': u.user_type or 'agent',
                    'is_online': bool(getattr(u, 'is_online', False)),
                    'email': u.email or '',
                    'provedor_nome': provedor.nome if provedor else ''
                }
                users_data.append(user_data)
            
            logger.info(f"[MY_PROVIDER_USERS] Retornando {len(users_data)} usuários para user {user.id}")
            return Response({'users': users_data})
        
        except Exception as e:
            # Retornar lista vazia em caso de erro
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[MY_PROVIDER_USERS] Erro ao buscar usuários: {e}", exc_info=True)
            return Response({'users': []})

    @action(detail=False, methods=['get'])
    def status(self, request):
        """
        Retorna o status online de todos os usuários que o usuário atual pode ver.
        """
        users = self.get_queryset()
        data = [
            {'id': user.id, 'is_online': user.is_online}
            for user in users
        ]
        return Response({'users': data})


class UsersPingView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        user = request.user
        if user.is_authenticated:
            from django.utils import timezone
            user.last_seen = timezone.now()
            user.is_online = True
            user.save(update_fields=['last_seen', 'is_online'])
            
            # Log de sucesso (debug)
            logger.debug(f"[PING] Usuário {user.username} (ID: {user.id}) atualizado com sucesso")
            
            return Response({'status': 'ok', 'last_seen': user.last_seen})
        
        # Log de falha de autenticação no ping
        auth_header = request.headers.get('Authorization', 'N/A')
        logger.warning(f"[PING] Falha de autenticação para request. Header: {auth_header[:20]}...")
        
        return Response({'error': 'Not authenticated'}, status=401)
    
    def get(self, request):
        return Response({'status': 'ok'})


class CanalViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar canais com isolamento por provedor
    """
    queryset = Canal.objects.all()
    serializer_class = CanalSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Verificação de segurança: garantir que usuário está autenticado
        if not user.is_authenticated:
            return Canal.objects.none()
        
        # Verificação segura de user_type
        user_type = getattr(user, 'user_type', None)
        
        # Superadmin vê todos os canais
        if user_type == 'superadmin':
            queryset = Canal.objects.all()
        else:
            # Outros usuários veem apenas canais do seu provedor (ISOLAMENTO POR PROVEDOR)
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                queryset = Canal.objects.filter(provedor__in=provedores)
            else:
                queryset = Canal.objects.none()
        
        # Filtrar por provedor se fornecido (ISOLAMENTO ADICIONAL)
        provedor_param = self.request.query_params.get('provedor_id')
        if provedor_param:
            try:
                provedor_id = int(provedor_param)
                queryset = queryset.filter(provedor__id=provedor_id)
            except (ValueError, TypeError):
                pass
        
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        user = self.request.user
        # Verificação de segurança
        if not user.is_authenticated:
            raise PermissionDenied('Usuário não autenticado')
        # Verificar permissões
        user_type = getattr(user, 'user_type', None)
        if user_type not in ['superadmin', 'admin']:
            raise PermissionDenied('Apenas administradores podem criar canais')
        
        # Obter provedor do request (pode vir como provedor_id no body ou query params)
        provedor = None
        provedor_id = self.request.data.get('provedor_id') or self.request.query_params.get('provedor_id')
        
        if provedor_id:
            try:
                provedor = Provedor.objects.get(id=int(provedor_id))
            except (Provedor.DoesNotExist, ValueError, TypeError):
                pass
        
        # Se não foi fornecido, usar o primeiro provedor do usuário
        if not provedor:
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                provedor = provedores.first()
            else:
                raise PermissionDenied('Usuário não possui provedor associado')
        
        # Garantir que o provedor pertence ao usuário (exceto superadmin)
        if user.user_type != 'superadmin':
            if provedor not in Provedor.objects.filter(admins=user):
                raise PermissionDenied('Você não tem permissão para criar canais neste provedor')
        
        # Salvar com provedor (mesmo sendo read_only no serializer, podemos passar no save)
        serializer.save(provedor=provedor)
    
    def create(self, request, *args, **kwargs):
        """Sobrescreve create para incluir telegram_code_sent na resposta"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Preparar resposta com dados do canal
        response_data = serializer.data
        
        # Para WhatsApp Oficial, apenas criar o canal sem redirecionar para OAuth
        # O usuário deve clicar em "Conectar" depois para iniciar o fluxo OAuth
        if serializer.instance and serializer.instance.tipo == 'whatsapp_oficial':
            # Canal criado, mas ainda não conectado (sem token/phone_number_id)
            # O frontend deve mostrar botão "Conectar" que chama o endpoint connect_whatsapp_official
            response_data['needs_connection'] = True
            response_data['message'] = 'Canal WhatsApp Oficial criado. Clique em "Conectar" para iniciar o fluxo OAuth.'
        
        # Adicionar resultado do código Telegram se disponível
        if hasattr(serializer, '_telegram_code_result') and serializer._telegram_code_result:
            response_data['telegram_code_sent'] = serializer._telegram_code_result
        
        headers = self.get_success_headers(serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)
    
    def update(self, request, *args, **kwargs):
        """Sobrescreve update para incluir telegram_code_sent na resposta"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Preparar resposta com dados do canal
        response_data = serializer.data
        
        # Adicionar resultado do código Telegram se disponível
        if hasattr(serializer, '_telegram_code_result') and serializer._telegram_code_result:
            response_data['telegram_code_sent'] = serializer._telegram_code_result
        
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        
        return Response(response_data)
    
    @action(detail=False, methods=['post'], url_path='verify-telegram-code')
    def verify_telegram_code(self, request):
        """
        Verifica o código de verificação do Telegram.
        
        Request body:
        {
            "channel_id": 87,  # OU
            "instance_name": "Telegram 123456",
            "code": "12345"
        }
        """
        import asyncio
        from .telegram_service import telegram_service
        
        channel_id = request.data.get('channel_id')
        instance_name = request.data.get('instance_name')
        code = request.data.get('code')
        
        if not code:
            return Response({
                'success': False,
                'error': 'code é obrigatório'
            }, status=400)
        
        # Buscar canal por ID ou nome
        canal = None
        if channel_id:
            try:
                canal = Canal.objects.get(id=channel_id)
            except Canal.DoesNotExist:
                pass
        
        if not canal and instance_name:
            canal = Canal.objects.filter(nome=instance_name, tipo='telegram').first()
        
        if not canal:
            return Response({
                'success': False,
                'error': 'Canal não encontrado. Forneça channel_id ou instance_name.'
            }, status=404)
        
        # Verificar permissões
        user = request.user
        if user.user_type != 'superadmin':
            provedores = Provedor.objects.filter(admins=user)
            if canal.provedor not in provedores:
                return Response({
                    'success': False,
                    'error': 'Você não tem permissão para este canal'
                }, status=403)
        
        try:
            # Executar verificação de forma síncrona
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(telegram_service.verify_code(canal, code))
            finally:
                loop.close()
            
            if result.get('success'):
                # O canal já foi atualizado pelo telegram_service.verify_code()
                # Apenas recarregar para garantir dados atualizados
                canal.refresh_from_db()
                
                return Response({
                    'success': True,
                    'message': 'Código verificado com sucesso!',
                    'user': result.get('user'),
                    'channel': {
                        'id': canal.id,
                        'status': canal.status,
                        'ativo': canal.ativo
                    }
                })
            elif result.get('requires_2fa'):
                return Response({
                    'success': False,
                    'requires_2fa': True,
                    'message': 'Verificação de dois fatores necessária'
                })
            else:
                return Response({
                    'success': False,
                    'error': result.get('error', 'Código inválido')
                }, status=400)
                
        except Exception as e:
            logger.error(f"Erro ao verificar código Telegram: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @action(detail=True, methods=['post'], url_path='connect-whatsapp-official')
    def connect_whatsapp_official(self, request, pk=None):
        """
        Conecta um canal WhatsApp Oficial existente ao Meta OAuth.
        
        Este endpoint deve ser chamado APÓS criar o canal WhatsApp Oficial.
        Ele gera a URL OAuth e retorna para o frontend redirecionar.
        
        Request: Nenhum body necessário, o canal_id vem da URL
        
        Response:
        {
            "success": true,
            "oauth_url": "https://www.facebook.com/v24.0/dialog/oauth?...",
            "redirect_uri": "https://api.niohub.com.br/api/auth/facebook/callback/",
            "channel_id": 123
        }
        """
        try:
            from integrations.meta_oauth import build_facebook_oauth_url
            from core.models import Provedor
            
            # Obter o canal
            canal = self.get_object()
            
            # Verificar se é WhatsApp Oficial
            if canal.tipo != 'whatsapp_oficial':
                return Response({
                    'success': False,
                    'error': 'Este endpoint é apenas para canais WhatsApp Oficial'
                }, status=400)
            
            # Verificar permissões
            user = request.user
            if user.user_type != 'superadmin':
                provedores = Provedor.objects.filter(admins=user)
                if canal.provedor not in provedores:
                    return Response({
                        'success': False,
                        'error': 'Você não tem permissão para conectar este canal'
                    }, status=403)
            
            # Obter provedor do canal
            provedor = canal.provedor
            if not provedor:
                return Response({
                    'success': False,
                    'error': 'Canal não possui provedor associado'
                }, status=400)
            
            # Obter config_id (opcional, usa padrão se não fornecido)
            config_id = request.data.get('config_id')
            if not config_id and provedor.integracoes_externas:
                config_id = provedor.integracoes_externas.get('meta_config_id')
            if not config_id:
                config_id = '1888449245359692'  # Fallback para config padrão
            
            # Gerar URL OAuth usando função centralizada
            try:
                oauth_url = build_facebook_oauth_url(provider_id=provedor.id, config_id=config_id)
                
                # Obter redirect_uri para retornar ao frontend (para debug/logging)
                from integrations.meta_oauth import get_backend_url
                backend_url = get_backend_url()
                redirect_uri = f"{backend_url}/api/auth/facebook/callback/"
                
                return Response({
                    'success': True,
                    'oauth_url': oauth_url,
                    'redirect_uri': redirect_uri,
                    'channel_id': canal.id,
                    'provider_id': provedor.id
                })
            except RuntimeError as e:
                # Erro ao obter BACKEND_URL
                return Response({
                    'success': False,
                    'error': str(e)
                }, status=500)
            
        except Exception as e:
            logger.error(f"Erro ao conectar canal WhatsApp Oficial: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @action(detail=False, methods=['post'])
    def get_whatsapp_official_oauth_url(self, request):
        """
        Gera a URL OAuth do Facebook para WhatsApp Oficial (Cloud API).
        
        FONTE ÚNICA DE VERDADE para geração da URL OAuth.
        O frontend NÃO deve construir a URL manualmente.
        
        POR QUE ESTE ENDPOINT EXISTE:
        - Centraliza a lógica de construção da URL OAuth no backend
        - Garante que redirect_uri seja sempre correto (usando BACKEND_URL)
        - Previne erros de "URL bloqueada" do Meta
        - Evita duplicação de lógica entre frontend e backend
        
        IMPORTANTE:
        - redirect_uri sempre usa BACKEND_URL do settings
        - NUNCA usa localhost em produção
        - Se BACKEND_URL não estiver configurado, retorna erro
        
        Request body:
        {
            "provider_id": 1,  # ID do provedor (obrigatório)
            "config_id": "1888449245359692"  # Config ID do Meta (opcional)
        }
        
        Response:
        {
            "success": true,
            "oauth_url": "https://www.facebook.com/v24.0/dialog/oauth?...",
            "redirect_uri": "https://api.niohub.com.br/api/auth/facebook/callback/"
        }
        """
        try:
            from integrations.meta_oauth import build_facebook_oauth_url
            from core.models import Provedor
            
            # Obter provedor do request
            provider_id = request.data.get('provider_id')
            if not provider_id:
                # Tentar obter do usuário logado
                user = request.user
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                    provider_id = provedor.id
                else:
                    return Response({
                        'success': False,
                        'error': 'provider_id não especificado'
                    }, status=400)
            
            try:
                provider_id = int(provider_id)
                provedor = Provedor.objects.get(id=provider_id)
            except (Provedor.DoesNotExist, ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Provedor não encontrado'
                }, status=404)
            
            # Verificar permissões (usuário deve ser admin do provedor ou superadmin)
            user = request.user
            if user.user_type != 'superadmin':
                if provedor not in Provedor.objects.filter(admins=user):
                    return Response({
                        'success': False,
                        'error': 'Você não tem permissão para acessar este provedor'
                    }, status=403)
            
            # Obter config_id (opcional, usa padrão se não fornecido)
            config_id = request.data.get('config_id') or provedor.meta_config_id
            
            # Gerar URL OAuth usando função centralizada
            try:
                oauth_url = build_facebook_oauth_url(provider_id=provider_id, config_id=config_id)
                
                # Obter redirect_uri para retornar ao frontend (para debug/logging)
                from integrations.meta_oauth import get_backend_url
                backend_url = get_backend_url()
                redirect_uri = f"{backend_url}/auth/facebook/callback/"
                
                return Response({
                    'success': True,
                    'oauth_url': oauth_url,
                    'redirect_uri': redirect_uri,
                    'provider_id': provider_id
                })
            except RuntimeError as e:
                # Erro ao obter BACKEND_URL
                return Response({
                    'success': False,
                    'error': str(e)
                }, status=500)
            
        except Exception as e:
            logger.error(f"Erro ao gerar URL OAuth: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @action(detail=True, methods=['GET', 'POST'], url_path='message-templates')
    def message_templates(self, request, pk=None):
        """
        Gerencia modelos de mensagem do WhatsApp.
        - GET: Lista todos os modelos de mensagem
        - POST: Cria um novo modelo de mensagem
        """
        try:
            canal = self.get_object()
            
            if canal.tipo != 'whatsapp_oficial':
                return Response({
                    'success': False,
                    'error': 'Este endpoint é apenas para canais WhatsApp Oficial'
                }, status=400)
            
            # GET: Listar modelos
            if request.method == 'GET':
                from integrations.whatsapp_templates import list_message_templates
                
                # Verificar pré-requisitos antes de chamar a API da Meta
                if not canal.waba_id:
                    return Response({
                        'success': True,
                        'templates': [],
                        'warning': 'Canal sem waba_id configurado. Configure o canal WhatsApp Oficial primeiro.'
                    })
                
                if not canal.token:
                    return Response({
                        'success': True,
                        'templates': [],
                        'warning': 'Canal sem token de acesso configurado.'
                    })
                
                success, templates, error = list_message_templates(canal)
                
                if success:
                    return Response({
                        'success': True,
                        'templates': templates or []
                    })
                else:
                    return Response({
                        'success': False,
                        'error': error or 'Erro ao listar modelos'
                    }, status=500)
            
            # POST: Criar modelo
            elif request.method == 'POST':
                name = request.data.get('name')
                category = request.data.get('category')
                language = request.data.get('language')
                components = request.data.get('components', [])
                parameter_format = request.data.get('parameter_format', 'positional')
                
                if not all([name, category, language]):
                    return Response({
                        'success': False,
                        'error': 'name, category e language são obrigatórios'
                    }, status=400)
                
                from integrations.whatsapp_templates import create_message_template
                
                success, template, error = create_message_template(
                    canal=canal,
                    name=name,
                    category=category,
                    language=language,
                    components=components,
                    parameter_format=parameter_format
                )
                
                if success:
                    return Response({
                        'success': True,
                        'template': template
                    }, status=201)
                else:
                    return Response({
                        'success': False,
                        'error': error or 'Erro ao criar modelo'
                    }, status=400)
                
        except Exception as e:
            logger.exception(f"Erro ao processar modelos: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @action(detail=True, methods=['DELETE'], url_path=r'message-templates/(?P<template_id>[^/.]+)')
    def delete_message_template(self, request, pk=None, template_id=None):
        """
        Deleta um modelo de mensagem específico.
        """
        try:
            canal = self.get_object()
            
            if canal.tipo != 'whatsapp_oficial':
                return Response({
                    'success': False,
                    'error': 'Este endpoint é apenas para canais WhatsApp Oficial'
                }, status=400)
            
            if not template_id:
                return Response({
                    'success': False,
                    'error': 'template_id é obrigatório'
                }, status=400)
            
            from integrations.whatsapp_templates import delete_message_template
            
            success, error = delete_message_template(canal, template_id)
            
            if success:
                return Response({
                    'success': True,
                    'message': 'Modelo deletado com sucesso'
                })
            else:
                return Response({
                    'success': False,
                    'error': error or 'Erro ao deletar modelo'
                }, status=400)
                
        except Exception as e:
            logger.exception("Erro ao deletar modelo")
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @action(detail=False, methods=['get'])
    def check_whatsapp_official_status(self, request):
        """
        Verifica o status da conexão WhatsApp Oficial para um provedor.
        
        Útil para verificar se o OAuth callback foi processado com sucesso.
        
        Query params:
        - provider_id: ID do provedor (obrigatório)
        
        Response:
        {
            "connected": true/false,
            "canal": {
                "id": 1,
                "nome": "WhatsApp Oficial",
                "status": "connected",
                "ativo": true,
                "waba_id": "...",
                "phone_number_id": "...",
                "phone_number": "+5511999999999",
                "token_expires_at": "2026-02-12T10:30:00"
            }
        }
        """
        try:
            provider_id = request.query_params.get('provider_id')
            if not provider_id:
                # Tentar obter do usuário logado
                user = request.user
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                    provider_id = provedor.id
                else:
                    return Response({
                        'success': False,
                        'error': 'provider_id não especificado'
                    }, status=400)
            
            try:
                provider_id = int(provider_id)
                provedor = Provedor.objects.get(id=provider_id)
            except (Provedor.DoesNotExist, ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Provedor não encontrado'
                }, status=404)
            
            # Verificar permissões
            user = request.user
            if user.user_type != 'superadmin':
                if provedor not in Provedor.objects.filter(admins=user):
                    return Response({
                        'success': False,
                        'error': 'Você não tem permissão para acessar este provedor'
                    }, status=403)
            
            # Buscar canal WhatsApp Oficial
            canal = Canal.objects.filter(
                provedor_id=provider_id,
                tipo='whatsapp_oficial'
            ).first()
            
            if not canal:
                return Response({
                    'connected': False,
                    'message': 'Canal WhatsApp Oficial não encontrado. OAuth ainda não foi concluído ou falhou.'
                })
            
            # Extrair informações do canal
            canal_data = {
                'id': canal.id,
                'nome': canal.nome,
                'status': canal.status,
                'ativo': canal.ativo,
                'waba_id': canal.waba_id,
                'phone_number_id': canal.phone_number_id,
                'phone_number': canal.phone_number,
            }
            
            # Adicionar informações de token se disponíveis
            if canal.dados_extras:
                if 'token_expires_at' in canal.dados_extras:
                    canal_data['token_expires_at'] = canal.dados_extras['token_expires_at']
                if 'token_type' in canal.dados_extras:
                    canal_data['token_type'] = canal.dados_extras['token_type']
                if 'display_phone_number' in canal.dados_extras:
                    canal_data['display_phone_number'] = canal.dados_extras['display_phone_number']
            
            return Response({
                'connected': canal.ativo and canal.status == 'connected',
                'canal': canal_data,
                'message': 'Canal WhatsApp Oficial encontrado e conectado' if (canal.ativo and canal.status == 'connected') else 'Canal encontrado mas não está ativo/conectado'
            })
            
        except Exception as e:
            logger.error(f"Erro ao verificar status WhatsApp Oficial: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def get_whatsapp_profile_picture(self, request):
        """
        Busca foto de perfil do WhatsApp Oficial ou sessão WhatsApp conectada.
        
        Request body:
        {
            "phone": "556392484773",  # Opcional para WhatsApp Oficial
            "instance_name": "WhatsApp 123456",  # Para sessões WhatsApp
            "integration_type": "uazapi",  # Para sessões WhatsApp
            "channel_id": 123  # ID do canal (opcional, busca automática se não fornecido)
        }
        
        Response:
        {
            "success": true,
            "profile_picture_url": "https://...",
            "message": "Foto de perfil atualizada com sucesso"
        }
        """
        try:
            import requests
            from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
            
            # Obter parâmetros do request
            phone = request.data.get('phone')
            instance_name = request.data.get('instance_name')
            integration_type = request.data.get('integration_type')
            channel_id = request.data.get('channel_id')
            
            # Buscar canal
            canal = None
            
            if channel_id:
                try:
                    canal = Canal.objects.get(id=channel_id)
                except Canal.DoesNotExist:
                    return Response({
                        'success': False,
                        'error': 'Canal não encontrado'
                    }, status=404)
            else:
                # Buscar canal WhatsApp Oficial do provedor do usuário
                user = request.user
                if user.user_type == 'superadmin':
                    # Superadmin pode buscar qualquer canal
                    if phone:
                        # Tentar encontrar canal WhatsApp Oficial que tenha este número
                        provedores = Provedor.objects.all()
                    else:
                        provedores = Provedor.objects.filter(admins=user)
                else:
                    provedores = Provedor.objects.filter(admins=user)
                
                # Buscar canal WhatsApp Oficial
                canal = Canal.objects.filter(
                    provedor__in=provedores,
                    tipo='whatsapp_oficial'
                ).first()
            
            if not canal:
                return Response({
                    'success': False,
                    'error': 'Canal WhatsApp Oficial não encontrado'
                }, status=404)
            
            # Verificar permissões
            user = request.user
            if user.user_type != 'superadmin':
                if canal.provedor not in Provedor.objects.filter(admins=user):
                    return Response({
                        'success': False,
                        'error': 'Você não tem permissão para acessar este canal'
                    }, status=403)
            
            # Para WhatsApp Oficial, buscar foto via Graph API
            if canal.tipo == 'whatsapp_oficial':
                if not canal.token or not canal.phone_number_id:
                    return Response({
                        'success': False,
                        'error': 'Canal não está conectado (faltam token ou phone_number_id)'
                    }, status=400)
                
                # Buscar foto de perfil via Graph API
                url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.phone_number_id}/whatsapp_business_profile"
                params = {
                    "fields": "profile_picture_url,about,description",
                    "access_token": canal.token
                }
                
                logger.info(f"[PROFILE_PICTURE] Buscando foto de perfil para phone_number_id {canal.phone_number_id}")
                
                resp = requests.get(url, params=params, timeout=8)
                
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data and len(data) > 0:
                        profile = data[0]
                        profile_pic = profile.get("profile_picture_url")
                        
                        if profile_pic:
                            # Cachear em dados_extras
                            extras = canal.dados_extras or {}
                            extras["profile_picture_url"] = profile_pic
                            extras["profilePicUrl"] = profile_pic
                            extras["business_profile"] = profile
                            canal.dados_extras = extras
                            canal.save(update_fields=["dados_extras"])
                            
                            logger.info(f"[PROFILE_PICTURE] Foto de perfil encontrada e cacheada: {profile_pic[:50]}...")
                            
                            return Response({
                                'success': True,
                                'profile_picture_url': profile_pic,
                                'message': 'Foto de perfil atualizada com sucesso'
                            })
                    else:
                        return Response({
                            'success': False,
                            'error': 'Perfil de negócio não encontrado'
                        }, status=404)
                else:
                    error_text = resp.text[:500]
                    logger.error(f"[PROFILE_PICTURE] Erro ao buscar foto: {resp.status_code} - {error_text}")
                    return Response({
                        'success': False,
                        'error': f'Erro ao buscar foto de perfil: {resp.status_code}',
                        'details': error_text
                    }, status=resp.status_code)
            
            # Para sessões WhatsApp (Uazapi)
            elif canal.tipo == 'whatsapp_session' and instance_name:
                from integrations.utils import fetch_whatsapp_profile_picture
                
                if not phone:
                    return Response({
                        'success': False,
                        'error': 'phone é obrigatório para sessões WhatsApp'
                    }, status=400)
                
                profile_pic_url = fetch_whatsapp_profile_picture(
                    phone=phone,
                    instance_name=instance_name,
                    integration_type=integration_type or 'uazapi',
                    provedor=canal.provedor
                )
                
                if profile_pic_url:
                    return Response({
                        'success': True,
                        'profile_picture_url': profile_pic_url,
                        'message': 'Foto de perfil atualizada com sucesso'
                    })
                else:
                    return Response({
                        'success': False,
                        'error': 'Não foi possível obter foto de perfil'
                    }, status=404)
            
            else:
                return Response({
                    'success': False,
                    'error': f'Tipo de canal não suportado: {canal.tipo}'
                }, status=400)
                
        except Exception as e:
            logger.error(f"[PROFILE_PICTURE] Erro ao buscar foto de perfil: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': f'Erro ao buscar foto de perfil: {str(e)}'
            }, status=500)

    @action(detail=False, methods=['get'])
    def get_whatsapp_oficial_info(self, request):
        """
        Busca informações dos números do WhatsApp Oficial conectados à WABA usando Graph API.
        
        Utiliza o mesmo endpoint e lógica testada no PowerShell:
        GET https://graph.facebook.com/v24.0/{WABA_ID}/phone_numbers?access_token={TOKEN}
        
        Retorna:
        - id (Phone Number ID)
        - display_phone_number (número formatado, ex: +55 94 9149-3481)
        - verified_name (nome verificado)
        - code_verification_status (status do código)
        
        Query params:
        - provider_id: ID do provedor (obrigatório)
        
        Response:
        {
            "success": true,
            "phone_numbers": [
                {
                    "id": "919180324608853",
                    "display_phone_number": "+55 94 9149-3481",
                    "verified_name": "Nio Chat",
                    "code_verification_status": "NOT_VERIFIED"
                }
            ]
        }
        """
        try:
            from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
            
            # Obter provider_id
            provider_id = request.query_params.get('provider_id')
            if not provider_id:
                # Tentar obter do usuário logado
                user = request.user
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                    provider_id = provedor.id
                else:
                    return Response({
                        'success': False,
                        'error': 'provider_id não especificado'
                    }, status=400)
            
            try:
                provider_id = int(provider_id)
                provedor = Provedor.objects.get(id=provider_id)
            except (Provedor.DoesNotExist, ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Provedor não encontrado'
                }, status=404)
            
            # Verificar permissões
            user = request.user
            if user.user_type != 'superadmin':
                if provedor not in Provedor.objects.filter(admins=user):
                    return Response({
                        'success': False,
                        'error': 'Você não tem permissão para acessar este provedor'
                    }, status=403)
            
            # Buscar canal WhatsApp Oficial
            canal = Canal.objects.filter(
                provedor_id=provider_id,
                tipo='whatsapp_oficial'
            ).first()
            
            if not canal:
                return Response({
                    'success': False,
                    'error': 'Canal WhatsApp Oficial não encontrado. OAuth ainda não foi concluído.'
                }, status=404)
            
            # Verificar se tem WABA ID e token
            if not canal.waba_id:
                return Response({
                    'success': False,
                    'error': 'WABA ID não encontrado no canal'
                }, status=400)
            
            if not canal.token:
                return Response({
                    'success': False,
                    'error': 'Token de acesso não encontrado no canal'
                }, status=400)
            
            # Fazer requisição para Graph API usando o mesmo endpoint do PowerShell
            # IMPORTANTE: Usar v24.0 conforme teste bem-sucedido
            url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{canal.waba_id}/phone_numbers"
            
            logger.info(f"Buscando phone numbers do WABA {canal.waba_id} usando {PHONE_NUMBERS_API_VERSION}")
            
            response = requests.get(
                url,
                params={"access_token": canal.token},
                timeout=30
            )
            
            if response.status_code != 200:
                error_text = response.text[:500]
                logger.error(f"Erro ao buscar phone numbers: {response.status_code} - {error_text}")
                return Response({
                    'success': False,
                    'error': f'Erro ao buscar phone numbers: {response.status_code}',
                    'details': error_text
                }, status=response.status_code)
            
            # Processar resposta
            data = response.json()
            phones_list = data.get("data", [])
            
            if not phones_list:
                return Response({
                    'success': True,
                    'phone_numbers': [],
                    'message': 'Nenhum número de telefone encontrado para este WABA'
                })
            
            # IMPORTANTE: Filtrar números de teste e priorizar números reais
            # Mesma lógica usada no OAuth callback e webhook
            real_phones = []
            test_phones = []
            
            for phone in phones_list:
                verified_name = phone.get("verified_name", "").lower()
                display_number = phone.get("display_phone_number", "")
                
                is_test = (
                    "test" in verified_name or
                    display_number.startswith("1555") or
                    display_number == "15551469924"
                )
                
                phone_data = {
                    "id": phone.get("id"),
                    "display_phone_number": display_number,
                    "verified_name": phone.get("verified_name", ""),
                    "code_verification_status": phone.get("code_verification_status", ""),
                    "is_test": is_test
                }
                
                if is_test:
                    test_phones.append(phone_data)
                else:
                    real_phones.append(phone_data)
            
            # Retornar números reais primeiro, depois números de teste
            phone_numbers = real_phones + test_phones
            
            logger.info(f"✓ {len(real_phones)} número(s) REAL(is) e {len(test_phones)} número(s) de TESTE encontrado(s) para WABA {canal.waba_id}")
            
            return Response({
                'success': True,
                'phone_numbers': phone_numbers,
                'waba_id': canal.waba_id,
                'has_real_numbers': len(real_phones) > 0,
                'has_test_numbers': len(test_phones) > 0
            })
            
        except Exception as e:
            logger.error(f"Erro ao buscar informações do WhatsApp Oficial: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @action(detail=False, methods=['get'])
    def check_whatsapp_official_status(self, request):
        """
        Verifica o status da conexão WhatsApp Oficial para um provedor.
        
        Útil para verificar se o OAuth callback foi processado com sucesso.
        
        Query params:
        - provider_id: ID do provedor (obrigatório)
        
        Response:
        {
            "connected": true/false,
            "canal": {
                "id": 1,
                "nome": "WhatsApp Oficial",
                "status": "connected",
                "ativo": true,
                "waba_id": "...",
                "phone_number_id": "...",
                "phone_number": "+5511999999999",
                "token_expires_at": "2026-02-12T10:30:00"
            }
        }
        """
        try:
            provider_id = request.query_params.get('provider_id')
            if not provider_id:
                # Tentar obter do usuário logado
                user = request.user
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                    provider_id = provedor.id
                else:
                    return Response({
                        'success': False,
                        'error': 'provider_id não especificado'
                    }, status=400)
            
            try:
                provider_id = int(provider_id)
                provedor = Provedor.objects.get(id=provider_id)
            except (Provedor.DoesNotExist, ValueError, TypeError):
                return Response({
                    'success': False,
                    'error': 'Provedor não encontrado'
                }, status=404)
            
            # Verificar permissões
            user = request.user
            if user.user_type != 'superadmin':
                if provedor not in Provedor.objects.filter(admins=user):
                    return Response({
                        'success': False,
                        'error': 'Você não tem permissão para acessar este provedor'
                    }, status=403)
            
            # Buscar canal WhatsApp Oficial
            canal = Canal.objects.filter(
                provedor_id=provider_id,
                tipo='whatsapp_oficial'
            ).first()
            
            if not canal:
                return Response({
                    'connected': False,
                    'message': 'Canal WhatsApp Oficial não encontrado. OAuth ainda não foi concluído ou falhou.'
                })
            
            # Extrair informações do canal
            canal_data = {
                'id': canal.id,
                'nome': canal.nome,
                'status': canal.status,
                'ativo': canal.ativo,
                'waba_id': canal.waba_id,
                'phone_number_id': canal.phone_number_id,
                'phone_number': canal.phone_number,
            }
            
            # Adicionar informações de token se disponíveis
            if canal.dados_extras:
                if 'token_expires_at' in canal.dados_extras:
                    canal_data['token_expires_at'] = canal.dados_extras['token_expires_at']
                if 'token_type' in canal.dados_extras:
                    canal_data['token_type'] = canal.dados_extras['token_type']
                if 'display_phone_number' in canal.dados_extras:
                    canal_data['display_phone_number'] = canal.dados_extras['display_phone_number']
            
            return Response({
                'connected': canal.ativo and canal.status == 'connected',
                'canal': canal_data,
                'message': 'Canal WhatsApp Oficial encontrado e conectado' if (canal.ativo and canal.status == 'connected') else 'Canal encontrado mas não está ativo/conectado'
            })
            
        except Exception as e:
            logger.error(f"Erro ao verificar status WhatsApp Oficial: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': 'Erro interno ao verificar status'
            }, status=500)
    
    @action(detail=False, methods=['post'])
    def whatsapp_embedded_signup_finish(self, request):
        """
        Processa o finish do WhatsApp Embedded Signup.
        
        Este endpoint é chamado pelo frontend quando recebe o evento
        FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING via postMessage.
        
        IMPORTANTE: O evento NÃO chega via webhook, apenas via postMessage no frontend.
        
        Request body:
        {
            "waba_id": "<CUSTOMER_WABA_ID>",
            "provider_id": <ID_DO_PROVIDER>
        }
        
        Response:
        {
            "success": true,
            "canal": {
                "id": 1,
                "waba_id": "...",
                "phone_number_id": "...",
                "status": "connected"
            },
            "message": "Embedded Signup finalizado com sucesso"
        }
        """
        try:
            from integrations.embedded_signup_finish import process_embedded_signup_finish
            
            waba_id = request.data.get('waba_id')
            provider_id = request.data.get('provider_id')
            channel_id = request.data.get('channel_id')
            code = request.data.get('code') # Suporte ao code do SDK
            
            # Dados adicionais do evento (opcionais)
            phone_number_id = request.data.get('phone_number_id')
            business_id = request.data.get('business_id')
            page_ids = request.data.get('page_ids', [])
            
            if not waba_id and not code:
                return Response({
                    'success': False,
                    'error': 'waba_id ou code é obrigatório'
                }, status=400)
            
            if not provider_id:
                # Tentar obter do usuário logado
                user = request.user
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                    provider_id = provedor.id
                else:
                    return Response({
                        'success': False,
                        'error': 'provider_id é obrigatório'
                    }, status=400)
            
            logger.info(f"Processando finish do Embedded Signup - waba_id: {waba_id}, channel_id: {channel_id}, code: {'presente' if code else 'ausente'}, provider_id: {provider_id}")
            
            # Processar finish
            success, canal, error_message = process_embedded_signup_finish(
                provider_id=provider_id,
                waba_id=waba_id,
                code=code,
                phone_number_id=phone_number_id,
                business_id=business_id,
                page_ids=page_ids,
                channel_id=channel_id
            )
            
            if not success:
                return Response({
                    'success': False,
                    'error': error_message or 'Erro ao processar finish do Embedded Signup'
                }, status=400)
            
            # Retornar dados do canal
            canal_data = {
                'id': canal.id,
                'nome': canal.nome,
                'waba_id': canal.waba_id,
                'phone_number_id': canal.phone_number_id,
                'phone_number': canal.phone_number,
                'status': canal.status,
                'ativo': canal.ativo,
            }
            
            if canal.dados_extras:
                if 'display_phone_number' in canal.dados_extras:
                    canal_data['display_phone_number'] = canal.dados_extras['display_phone_number']
                if 'verified_name' in canal.dados_extras:
                    canal_data['verified_name'] = canal.dados_extras['verified_name']
                if 'code_verification_status' in canal.dados_extras:
                    canal_data['code_verification_status'] = canal.dados_extras['code_verification_status']
                if 'quality_rating' in canal.dados_extras:
                    canal_data['quality_rating'] = canal.dados_extras['quality_rating']
            
            return Response({
                'success': True,
                'canal': canal_data,
                'message': 'Embedded Signup finalizado com sucesso. Sincronizações iniciadas.'
            })
            
        except Exception as e:
            logger.error(f"Erro ao processar finish do Embedded Signup: {str(e)}", exc_info=True)
            return Response({
                'success': False,
                'error': f'Erro interno: {str(e)}'
            }, status=500)
    
    @action(detail=False, methods=['post'])
    def get_whatsapp_session_qr(self, request):
        """
        Gera QR code ou código de pareamento para conectar WhatsApp via Uazapi
        """
        try:
            from core.uazapi_client import UazapiClient
            from core.models import Provedor
            
            # Obter provedor do request
            provedor_id = request.data.get('provedor_id')
            if not provedor_id:
                # Tentar obter do usuário logado
                user = request.user
                if hasattr(user, 'provedores_admin') and user.provedores_admin.exists():
                    provedor = user.provedores_admin.first()
                    provedor_id = provedor.id
                else:
                    return Response({
                        'success': False,
                        'error': 'Provedor não especificado'
                    }, status=400)
            
            try:
                provedor = Provedor.objects.get(id=provedor_id)
            except Provedor.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Provedor não encontrado'
                }, status=404)
            
            # Obter credenciais Uazapi do provedor
            uazapi_token = None
            uazapi_url = None
            
            # Buscar na integração WhatsApp
            from integrations.models import WhatsAppIntegration
            whatsapp_integration = WhatsAppIntegration.objects.filter(provedor=provedor).first()
            if whatsapp_integration:
                uazapi_token = whatsapp_integration.access_token
                uazapi_url = (
                    whatsapp_integration.settings.get('whatsapp_url')
                    if whatsapp_integration.settings else None
                )
            
            # Fallback para integracoes_externas
            if not uazapi_token or uazapi_token == '':
                integracoes = provedor.integracoes_externas or {}
                uazapi_token = integracoes.get('whatsapp_token')
            if not uazapi_url or uazapi_url == '':
                integracoes = provedor.integracoes_externas or {}
                uazapi_url = integracoes.get('whatsapp_url')
            
            if not uazapi_token or not uazapi_url:
                return Response({
                    'success': False,
                    'error': 'Token ou URL do Uazapi não configurados para este provedor'
                }, status=400)
            
            # Obter nome da instância do request (opcional)
            instance_name = request.data.get('instance_name')
            phone = request.data.get('phone')  # Se fornecido, gera código de pareamento
            
            # Criar cliente Uazapi
            uazapi = UazapiClient(base_url=uazapi_url, token=uazapi_token)
            
            # Conectar instância (gera QR code se phone=None, ou código de pareamento se phone fornecido)
            resultado = uazapi.connect_instance(phone=phone, instance_name=instance_name)
            
            # Verificar se houve erro
            if 'error' in resultado:
                return Response({
                    'success': False,
                    'error': resultado.get('error', 'Erro desconhecido'),
                    'message': resultado.get('message', 'Erro ao conectar instância')
                }, status=500)
            
            # A Uazapi retorna o QR code dentro de resultado['instance']['qrcode']
            # Estrutura: {'connected': True, 'instance': {'qrcode': 'data:image/png;base64,...', 'paircode': '', ...}}
            
            # Extrair QR code do resultado
            qrcode = None
            paircode = None
            
            # Primeiro, tentar buscar dentro de 'instance' (formato padrão da Uazapi)
            if 'instance' in resultado and isinstance(resultado['instance'], dict):
                instance = resultado['instance']
                if 'qrcode' in instance and instance['qrcode']:
                    qrcode = instance['qrcode']
                elif 'base64' in instance and instance['base64']:
                    qrcode = instance['base64']
                elif 'base64Image' in instance and instance['base64Image']:
                    qrcode = instance['base64Image']
                
                # Extrair paircode do instance
                if 'paircode' in instance and instance['paircode']:
                    paircode = instance['paircode']
            
            # Se não encontrou no instance, tentar no nível raiz (fallback)
            if not qrcode:
                if 'qrcode' in resultado and resultado['qrcode']:
                    qrcode = resultado['qrcode']
                elif 'base64' in resultado and resultado['base64']:
                    qrcode = resultado['base64']
                elif 'base64Image' in resultado and resultado['base64Image']:
                    qrcode = resultado['base64Image']
                elif 'qrcode_base64' in resultado and resultado['qrcode_base64']:
                    qrcode = resultado['qrcode_base64']
            
            # Se o QR code não começa com "data:image", adicionar o prefixo
            if qrcode and not qrcode.startswith('data:image') and not qrcode.startswith('http'):
                qrcode = f"data:image/png;base64,{qrcode}"
            
            # Extrair código de pareamento se ainda não encontrou
            if not paircode:
                if 'paircode' in resultado and resultado['paircode']:
                    paircode = resultado['paircode']
                elif 'code' in resultado and resultado['code']:
                    paircode = resultado['code']
            
            # Retornar no formato esperado pelo frontend
            # O frontend espera res.data.qrcode diretamente (string) ou res.data como objeto com qrcode/paircode
            response_data = {}
            if qrcode:
                response_data['qrcode'] = qrcode
            if paircode:
                response_data['paircode'] = paircode
            
            # Se não encontrou QR code nem paircode, tentar extrair do resultado completo
            if not response_data:
                # Tentar extrair de outros campos possíveis no nível raiz
                for key in ['qrcode', 'base64', 'base64Image', 'qrcode_base64', 'image']:
                    if key in resultado and resultado[key]:
                        qrcode = resultado[key]
                        if not qrcode.startswith('data:image') and not qrcode.startswith('http'):
                            qrcode = f"data:image/png;base64,{qrcode}"
                        response_data['qrcode'] = qrcode
                        break
                
                # Tentar extrair paircode
                for key in ['paircode', 'code', 'pairing_code']:
                    if key in resultado and resultado[key]:
                        response_data['paircode'] = resultado[key]
                        break
            
            # Se ainda não encontrou nada, retornar erro
            if not response_data:
                logger.error(f"Não foi possível extrair QR code ou paircode da resposta da Uazapi.")
                return Response({
                    'success': False,
                    'error': 'QR code não encontrado na resposta da API',
                    'message': 'A API Uazapi não retornou um QR code válido'
                }, status=500)
            
            # Retornar no formato que o frontend espera
            # O frontend verifica: res.data.qrcode (string) OU res.data como objeto
            return Response({
                'success': True,
                **response_data  # qrcode e/ou paircode diretamente no nível raiz
            })
            
        except Exception as e:
            logger.error(f"Erro ao gerar QR code WhatsApp: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @action(detail=False, methods=['post'])
    def connect_whatsapp_session(self, request):
        """
        Conecta uma sessão WhatsApp via Uazapi (alias para get_whatsapp_session_qr)
        """
        return self.get_whatsapp_session_qr(request)
    
    @action(detail=True, methods=['post'])
    def get_whatsapp_session_status(self, request, pk=None):
        """
        Verifica o status de uma sessão WhatsApp conectada via Uazapi
        """
        try:
            from core.uazapi_client import UazapiClient
            from core.models import Provedor
            
            # Obter canal - usar pk do parâmetro se não vier do get_object
            if pk is None:
                pk = self.kwargs.get('pk')
            
            try:
                canal = self.get_object()
            except Exception as e:
                logger.error(f"Erro ao obter canal com pk={pk}: {e}", exc_info=True)
                return Response({
                    'success': False,
                    'error': f'Canal não encontrado: {str(e)}'
                }, status=404)
            
            if not canal:
                return Response({
                    'success': False,
                    'error': 'Canal não encontrado'
                }, status=404)
            
            provedor = canal.provedor
            
            # Obter credenciais Uazapi do provedor
            uazapi_token = None
            uazapi_url = None
            
            # Buscar na integração WhatsApp
            from integrations.models import WhatsAppIntegration
            whatsapp_integration = WhatsAppIntegration.objects.filter(provedor=provedor).first()
            if whatsapp_integration:
                uazapi_token = whatsapp_integration.access_token
                uazapi_url = (
                    whatsapp_integration.settings.get('whatsapp_url')
                    if whatsapp_integration.settings else None
                )
            
            # Fallback para integracoes_externas
            if not uazapi_token or uazapi_token == '':
                integracoes = provedor.integracoes_externas or {}
                uazapi_token = integracoes.get('whatsapp_token')
            if not uazapi_url or uazapi_url == '':
                integracoes = provedor.integracoes_externas or {}
                uazapi_url = integracoes.get('whatsapp_url')
            
            if not uazapi_token or not uazapi_url:
                return Response({
                    'success': False,
                    'error': 'Token ou URL do Uazapi não configurados para este provedor'
                }, status=400)
            
            # Obter instance_id do canal ou do request
            instance_id = request.data.get('instance_id')
            
            if not instance_id:
                # Tentar buscar do dados_extras do canal
                if canal.dados_extras:
                    instance_id = canal.dados_extras.get('instance')
            
            if not instance_id:
                # Tentar buscar do nome do canal ou phone_number
                instance_id = canal.phone_number or canal.nome
            
            if not instance_id:
                return Response({
                    'success': False,
                    'error': 'ID da instância não encontrado. Forneça instance_id no body da requisição ou configure no canal.',
                    'details': {
                        'canal_id': canal.id,
                        'canal_nome': canal.nome,
                        'dados_extras': canal.dados_extras,
                        'phone_number': canal.phone_number
                    }
                }, status=400)
            
            # Criar cliente Uazapi
            uazapi = UazapiClient(base_url=uazapi_url, token=uazapi_token)
            
            # Buscar status da instância
            try:
                status_data = uazapi.get_instance_status(instance_id)
                return Response({
                    'success': True,
                    'data': status_data
                })
            except requests.exceptions.HTTPError as e:
                logger.error(f"Erro HTTP ao buscar status da instância: {e}", exc_info=True)
                return Response({
                    'success': False,
                    'error': f'Erro ao buscar status: {str(e)}'
                }, status=500)
            except Exception as e:
                logger.error(f"Erro ao buscar status da instância: {e}", exc_info=True)
                return Response({
                    'success': False,
                    'error': str(e)
                }, status=500)
            
        except Exception as e:
            logger.error(f"Erro ao verificar status WhatsApp: {e}", exc_info=True)
            return Response({
                'success': False,
                'error': str(e)
            }, status=500)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para visualizar logs de auditoria com isolamento por provedor
    Apenas leitura (ReadOnly) para manter integridade dos logs
    IMPORTANTE: Quando conversation_closed=true, busca SEMPRE do Supabase
    """
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def list(self, request, *args, **kwargs):
        """
        Lista logs de auditoria
        IMPORTANTE: SEMPRE busca do Supabase - nunca do banco local
        A página de auditoria deve sempre usar dados do Supabase
        """
        conversation_closed = request.query_params.get('conversation_closed', '').lower() == 'true'
        conversation_id_param = request.query_params.get('conversation_id')
        
        # SEMPRE buscar do Supabase para auditoria (não usar banco local)
        try:
            import logging
            import requests
            from django.conf import settings
            logger = logging.getLogger(__name__)
            
            # Obter provedor_id
            provedor_id = None
            provedor_param = request.query_params.get('provedor_id')
            if provedor_param:
                try:
                    provedor_id = int(provedor_param)
                except (ValueError, TypeError):
                    pass
            
            if not provedor_id:
                user = request.user
                if user.user_type == 'admin':
                    # Usar o mesmo padrão dos outros ViewSets: user.provedores_admin.all()
                    provedores = user.provedores_admin.all()
                    if provedores.exists():
                        provedor_id = provedores.first().id
                elif hasattr(user, 'provedor_id') and user.provedor_id:
                    provedor_id = user.provedor_id
                elif hasattr(user, 'provedor') and user.provedor:
                    provedor_id = user.provedor.id
            
            # Configurar Supabase
            supabase_url = getattr(settings, 'SUPABASE_URL', '').rstrip('/')
            supabase_key = getattr(settings, 'SUPABASE_SERVICE_ROLE_KEY', '') or getattr(settings, 'SUPABASE_ANON_KEY', '')
            
            if not supabase_url or not supabase_key:
                logger.error("[AUDIT-LOGS] Supabase não configurado! Configure SUPABASE_URL e SUPABASE_ANON_KEY no .env")
                # Retornar lista vazia se Supabase não estiver configurado (não usar banco local)
                from rest_framework.response import Response
                return Response({
                    'count': 0,
                    'results': [],
                    'next': None,
                    'previous': None
                })
            
            headers = {
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
                "Content-Type": "application/json",
            }
            
            if provedor_id:
                headers["X-Provedor-ID"] = str(provedor_id)
            
            # Buscar audit logs do Supabase
            audit_url = f"{supabase_url}/rest/v1/{getattr(settings, 'SUPABASE_AUDIT_TABLE', 'auditoria')}"
            params = {}
            
            if provedor_id:
                params['provedor_id'] = f'eq.{provedor_id}'
            
            if conversation_id_param:
                try:
                    conv_id = int(conversation_id_param)
                    params['conversation_id'] = f'eq.{conv_id}'
                except (ValueError, TypeError):
                    pass
            
            # Filtrar apenas conversas encerradas se conversation_closed=true
            if conversation_closed:
                params['action'] = 'in.(conversation_closed_ai,conversation_closed_manual,conversation_closed_agent,conversation_closed_timeout)'
                # Ordenar por ended_at quando é conversation_closed
                params['order'] = 'ended_at.desc'
            elif conversation_id_param:
                # Quando busca por conversation_id, buscar todos os logs dessa conversa
                # Ordenar por timestamp (pode ser ended_at ou created_at)
                params['order'] = 'ended_at.desc,created_at.desc'
            else:
                # Ordenar por timestamp descendente
                params['order'] = 'ended_at.desc'
            
            # Limite de resultados (aceita page_size e limit)
            raw_limit = request.query_params.get('limit') or request.query_params.get('page_size') or '50'
            try:
                limit_value = int(raw_limit)
            except (ValueError, TypeError):
                limit_value = 50
            params['limit'] = limit_value
            
            logger.info(f"[AUDIT-LOGS] Buscando do Supabase: {params}")
            response = requests.get(audit_url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                audit_logs = response.json()
                if not isinstance(audit_logs, list):
                    audit_logs = []
                
                logger.info(f"[AUDIT-LOGS] {len(audit_logs)} logs encontrados no Supabase")
                
                # SEMPRE retornar dados do Supabase (mesmo se vazio)
                # NÃO fazer fallback para banco local
                
                # Coletar todos os conversation_ids únicos para buscar dados em lote
                conversation_ids = set()
                user_ids = set()
                for log in audit_logs:
                    conv_id = log.get('conversation_id')
                    if conv_id:
                        try:
                            conversation_ids.add(int(conv_id))
                        except (ValueError, TypeError):
                            pass
                    log_user_id = log.get('user_id')
                    if log_user_id is not None:
                        try:
                            user_ids.add(int(log_user_id))
                        except (ValueError, TypeError):
                            pass
                
                # Buscar todas as conversas de uma vez (otimização)
                conversations_data = {}
                if conversation_ids:
                    conv_url = f"{supabase_url}/rest/v1/conversations"
                    # Buscar todas as conversas de uma vez usando 'in'
                    conv_ids_str = ','.join(str(cid) for cid in conversation_ids)
                    conv_params = {'id': f'in.({conv_ids_str})', 'select': 'id,contact_id,inbox_id,created_at,updated_at,ended_at'}
                    conv_response = requests.get(conv_url, headers=headers, params=conv_params, timeout=10)
                    if conv_response.status_code == 200:
                        convs = conv_response.json()
                        if convs and isinstance(convs, list):
                            for conv in convs:
                                conversations_data[conv.get('id')] = conv
                
                # Coletar todos os contact_ids únicos
                contact_ids = set()
                for conv_data in conversations_data.values():
                    contact_id = conv_data.get('contact_id')
                    if contact_id:
                        contact_ids.add(contact_id)
                
                # Buscar todos os contatos de uma vez (otimização)
                contacts_data = {}
                if contact_ids:
                    contact_url = f"{supabase_url}/rest/v1/contacts"
                    contact_ids_str = ','.join(str(cid) for cid in contact_ids)
                    contact_params = {'id': f'in.({contact_ids_str})', 'select': 'id,name,phone,avatar'}
                    contact_response = requests.get(contact_url, headers=headers, params=contact_params, timeout=10)
                    if contact_response.status_code == 200:
                        contacts = contact_response.json()
                        if contacts and isinstance(contacts, list):
                            for contact in contacts:
                                contacts_data[contact.get('id')] = contact
                
                # NOTA: A tabela 'inboxes' não existe no Supabase
                # O channel_type será extraído dos detalhes do audit log ou da conversa
                inboxes_data = {}

                # Resolver nomes de usuários locais para exibir "quem fez a ação"
                users_data = {}
                if user_ids:
                    try:
                        users = User.objects.filter(id__in=list(user_ids)).only(
                            'id', 'first_name', 'last_name', 'username'
                        )
                        for u in users:
                            display_name = f"{u.first_name} {u.last_name}".strip() or u.username or f"Usuário {u.id}"
                            users_data[u.id] = display_name
                    except Exception as users_err:
                        logger.warning(f"[AUDIT-LOGS] Erro ao resolver nomes de usuários: {users_err}")
                
                # Formatar dados para o formato esperado pelo frontend
                formatted_logs = []
                for log in audit_logs:
                    conv_id = log.get('conversation_id')
                    conv_data = conversations_data.get(conv_id) if conv_id else {}
                    contact_id = conv_data.get('contact_id') if conv_data else None
                    contact_data = contacts_data.get(contact_id) if contact_id else {}
                    inbox_id = conv_data.get('inbox_id') if conv_data else None
                    inbox_data = inboxes_data.get(inbox_id) if inbox_id else {}
                    
                    # Extrair detalhes do log
                    details = log.get('details', {})
                    if isinstance(details, str):
                        try:
                            import json
                            details = json.loads(details)
                        except:
                            details = {}
                    elif not isinstance(details, dict):
                        details = {}
                    
                    # Extrair channel_type de várias fontes possíveis
                    channel_type = None
                    
                    # 1. Tentar dos detalhes do audit log (string)
                    if isinstance(details, dict):
                        details_str = details.get('details', '')
                        if isinstance(details_str, str):
                            if 'whatsapp' in details_str.lower():
                                channel_type = 'whatsapp'
                            elif 'telegram' in details_str.lower():
                                channel_type = 'telegram'
                            elif 'email' in details_str.lower():
                                channel_type = 'email'
                            elif 'webchat' in details_str.lower():
                                channel_type = 'webchat'
                            elif 'facebook' in details_str.lower():
                                channel_type = 'facebook'
                            elif 'instagram' in details_str.lower():
                                channel_type = 'instagram'
                        
                        # 2. Tentar do campo channel_type direto
                        if not channel_type:
                            channel_type = details.get('channel_type')
                    
                    # 3. Padrão se não encontrou
                    if not channel_type:
                        channel_type = 'whatsapp'  # Padrão mais comum
                    
                    formatted_log = {
                        'id': log.get('id'),
                        'action': log.get('action'),
                        'details': details,
                        'user_id': log.get('user_id'),
                        'user': users_data.get(log.get('user_id')) if log.get('user_id') is not None else None,
                        'provedor_id': log.get('provedor_id'),
                        'conversation_id': conv_id,
                        'contact_name': contact_data.get('name') if contact_data else (details.get('contact_name') if isinstance(details, dict) else None),
                        'contact_photo': contact_data.get('avatar') if contact_data else None,
                        'channel_type': channel_type,
                        'created_at': conv_data.get('created_at') if conv_data else (log.get('ended_at') or log.get('created_at')),
                        'ended_at': conv_data.get('ended_at') if conv_data else log.get('ended_at'),
                        'updated_at': conv_data.get('updated_at') if conv_data else None,
                        'timestamp': log.get('ended_at') or log.get('created_at'),
                    }
                    
                    formatted_logs.append(formatted_log)
                
                # Mesclar logs locais relevantes (algumas ações não são enviadas ao Supabase)
                if provedor_id and not conversation_closed and not conversation_id_param:
                    try:
                        local_actions = [
                            'login', 'logout',
                            'create', 'edit', 'delete',
                            'contact_created',
                            'conversation_closed_ai',
                            'conversation_closed_agent',
                            'conversation_closed_manual',
                            'conversation_closed_timeout',
                            'conversation_assigned',
                        ]
                        local_auth_logs = AuditLog.objects.filter(
                            provedor_id=provedor_id,
                            action__in=local_actions
                        ).select_related('user').order_by('-timestamp')[:max(limit_value * 2, 100)]

                        for log in local_auth_logs:
                            formatted_logs.append({
                                'id': f"local-{log.id}",
                                'action': log.action,
                                'details': {'details': log.details} if log.details else {},
                                'user_id': log.user_id,
                                'user': str(log.user) if log.user else None,
                                'provedor_id': provedor_id,
                                'conversation_id': None,
                                'contact_name': None,
                                'contact_photo': None,
                                'channel_type': None,
                                'created_at': log.timestamp,
                                'ended_at': log.timestamp,
                                'updated_at': log.timestamp,
                                'timestamp': log.timestamp,
                            })
                    except Exception as local_err:
                        logger.warning(f"[AUDIT-LOGS] Erro ao mesclar login/logout local: {local_err}")

                # Ordenação global + limite final após merge
                def _ts(item):
                    from django.utils.dateparse import parse_datetime
                    value = item.get('timestamp') or item.get('ended_at') or item.get('created_at')
                    if isinstance(value, datetime):
                        return value
                    if isinstance(value, str):
                        parsed = parse_datetime(value)
                        if parsed:
                            return parsed
                    return datetime.min

                formatted_logs = sorted(formatted_logs, key=_ts, reverse=True)[:limit_value]

                # Retornar no formato paginado esperado pelo frontend
                from rest_framework.response import Response
                return Response({
                    'count': len(formatted_logs),
                    'results': formatted_logs,
                    'next': None,
                    'previous': None
                })
            else:
                logger.error(f"[AUDIT-LOGS] Erro ao buscar do Supabase: {response.status_code} - {response.text}")
                # NÃO fazer fallback - retornar lista vazia
                from rest_framework.response import Response
                return Response({
                    'count': 0,
                    'results': [],
                    'next': None,
                    'previous': None
                })
                    
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[AUDIT-LOGS] Erro ao buscar do Supabase: {e}", exc_info=True)
            # NÃO fazer fallback - retornar lista vazia
            from rest_framework.response import Response
            return Response({
                'count': 0,
                'results': [],
                'next': None,
                'previous': None
            })
    
    def get_queryset(self):
        """
        Retorna queryset de logs de auditoria com isolamento por provedor.
        IMPORTANTE: Este método só é usado quando não há parâmetro conversation_closed=true.
        Quando conversation_closed=true, o método list() busca diretamente do Supabase.
        """
        try:
            user = self.request.user
            
            # Superadmin vê todos os logs
            if user.user_type == 'superadmin':
                queryset = AuditLog.objects.all()
            else:
                # Outros usuários veem apenas logs do seu provedor (ISOLAMENTO POR PROVEDOR)
                # Usar o mesmo padrão dos outros ViewSets: user.provedores_admin.all()
                provedores = user.provedores_admin.all()
                if provedores.exists():
                    queryset = AuditLog.objects.filter(provedor__in=provedores)
                else:
                    queryset = AuditLog.objects.none()
            
            # Filtrar por provedor se fornecido (ISOLAMENTO ADICIONAL)
            provedor_param = self.request.query_params.get('provedor_id')
            if provedor_param:
                try:
                    provedor_id = int(provedor_param)
                    queryset = queryset.filter(provedor__id=provedor_id)
                except (ValueError, TypeError):
                    pass
            
            # Ordenar antes de aplicar slice (se houver limite)
            queryset = queryset.order_by('-timestamp')
            
            # Filtrar por limite se fornecido (APÓS order_by)
            limit = self.request.query_params.get('limit')
            if limit:
                try:
                    limit = int(limit)
                    queryset = queryset[:limit]
                except (ValueError, TypeError):
                    pass
            
            return queryset
        except Exception as e:
            logger.error(f"[AUDIT-LOGS] Erro no get_queryset: {e}", exc_info=True)
            # Retornar queryset vazio em caso de erro
            return AuditLog.objects.none()

class SystemConfigView(APIView):
    """
    View para gerenciar configurações do sistema
    Retorna/atualiza um único objeto SystemConfig
    Apenas superadmin pode acessar
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def check_permissions(self, request):
        """Verificar se o usuário é superadmin"""
        if not request.user.is_authenticated:
            raise permissions.NotAuthenticated()
        if request.user.user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode acessar configurações do sistema')
    
    def get(self, request):
        """Retorna a configuração do sistema (ou cria uma padrão se não existir)"""
        self.check_permissions(request)
        try:
            # Buscar ou criar configuração padrão
            # Verificar se o campo 'key' existe no banco antes de usar
            try:
                config = SystemConfig.objects.filter(key='system_config').first()
            except Exception as db_error:
                # Se o campo 'key' não existe, buscar qualquer SystemConfig ou criar um novo
                logger.warning(f"Campo 'key' não encontrado, usando fallback: {db_error}")
                config = SystemConfig.objects.first()
            
            if not config:
                # Criar configuração padrão
                try:
                    config = SystemConfig.objects.create(
                        key='system_config',
                        value='{}',
                        description='Configurações gerais do sistema',
                        is_active=True
                    )
                except Exception as create_error:
                    logger.error(f"Erro ao criar SystemConfig padrão: {create_error}", exc_info=True)
                    # Se falhar ao criar, retornar dados padrão sem salvar no banco
                    return Response({
                        'id': 1,
                        'key': 'system_config',
                        'value': '{}',
                        'description': 'Configurações gerais do sistema',
                        'is_active': True,
                        'site_name': 'Nio Chat',
                        'contact_email': '',
                        'default_language': 'pt-br',
                        'timezone': 'America/Sao_Paulo',
                        'allow_public_signup': False,
                        'max_users_per_company': 10,
                        'google_api_key': '',
                        'openai_transcription_api_key': '',
                        'sgp_app': '',
                        'sgp_token': '',
                        'sgp_url': ''
                    })
            
            # Garantir que o objeto existe antes de serializar
            if not config or not hasattr(config, 'id'):
                return Response({
                    'id': 1,
                    'key': 'system_config',
                    'value': '{}',
                    'description': 'Configurações gerais do sistema',
                    'is_active': True,
                    'site_name': 'Nio Chat',
                    'contact_email': '',
                    'default_language': 'pt-br',
                    'timezone': 'America/Sao_Paulo',
                    'allow_public_signup': False,
                    'max_users_per_company': 10,
                    'google_api_key': '',
                    'openai_transcription_api_key': '',
                    'sgp_app': '',
                    'sgp_token': '',
                    'sgp_url': ''
                })
            
            try:
                serializer = SystemConfigSerializer(config)
                return Response(serializer.data)
            except Exception as serialize_error:
                logger.error(f"Erro ao serializar SystemConfig: {serialize_error}", exc_info=True)
                # Retornar dados básicos se a serialização falhar
                return Response({
                    'id': config.id,
                    'key': getattr(config, 'key', 'system_config'),
                    'value': getattr(config, 'value', '{}'),
                    'description': getattr(config, 'description', ''),
                    'is_active': getattr(config, 'is_active', True),
                    'site_name': 'Nio Chat',
                    'contact_email': '',
                    'default_language': 'pt-br',
                    'timezone': 'America/Sao_Paulo',
                    'allow_public_signup': False,
                    'max_users_per_company': 10,
                    'google_api_key': getattr(config, 'google_api_key', '') or '',
                    'openai_transcription_api_key': getattr(config, 'openai_transcription_api_key', '') or '',
                    'sgp_app': getattr(config, 'sgp_app', '') or '',
                    'sgp_token': getattr(config, 'sgp_token', '') or '',
                    'sgp_url': getattr(config, 'sgp_url', '') or ''
                })
            
        except Exception as e:
            logger.error(f"Erro ao buscar configurações do sistema: {e}", exc_info=True)
            # Retornar estrutura mínima em caso de erro
            return Response({
                'id': 1,
                'key': 'system_config',
                'value': '{}',
                'description': 'Configurações gerais do sistema',
                'is_active': True,
                'site_name': 'Nio Chat',
                'contact_email': '',
                'default_language': 'pt-br',
                'timezone': 'America/Sao_Paulo',
                'allow_public_signup': False,
                'max_users_per_company': 10,
                'google_api_key': '',
                'openai_transcription_api_key': '',
                'sgp_app': '',
                'sgp_token': '',
                'sgp_url': '',
                'error': 'Erro ao carregar configurações completas'
            }, status=200)  # Retornar 200 mesmo com erro parcial para não quebrar o frontend
    
    def put(self, request, pk=None):
        """Atualiza a configuração do sistema"""
        self.check_permissions(request)
        try:
            # Se pk não foi fornecido, usar 1 como padrão
            if not pk:
                pk = request.data.get('id', 1)
            
            # Buscar ou criar configuração
            # Verificar se o campo 'key' existe no banco antes de usar
            try:
                config = SystemConfig.objects.filter(key='system_config').first()
            except Exception as db_error:
                # Se o campo 'key' não existe, buscar qualquer SystemConfig ou criar um novo
                logger.warning(f"Campo 'key' não encontrado, usando fallback: {db_error}")
                config = SystemConfig.objects.first()
            
            if not config:
                try:
                    config = SystemConfig.objects.create(
                        key='system_config',
                        value='{}',
                        description='Configurações gerais do sistema',
                        is_active=True
                    )
                except Exception as create_error:
                    # Se falhar ao criar com 'key', criar sem 'key' (para bancos antigos)
                    logger.warning(f"Erro ao criar com 'key', tentando sem: {create_error}")
                    config = SystemConfig.objects.create(
                        value='{}',
                        description='Configurações gerais do sistema',
                        is_active=True
                    )
            
            logger.info(f"[SYSTEM_CONFIG] Dados recebidos no PUT: {list(request.data.keys())}")
            logger.info(f"[SYSTEM_CONFIG] google_api_key em request.data: {'google_api_key' in request.data}")
            if 'google_api_key' in request.data:
                logger.info(f"[SYSTEM_CONFIG] Valor de google_api_key: {request.data.get('google_api_key', '')[:30]}... (tamanho: {len(request.data.get('google_api_key', ''))})")
            
            serializer = SystemConfigSerializer(config, data=request.data, partial=True)
            
            if serializer.is_valid():
                logger.info("[SYSTEM_CONFIG] Serializer válido, salvando...")
                serializer.save()
                logger.info("[SYSTEM_CONFIG] Configuração salva com sucesso")
                return Response(serializer.data)
            else:
                logger.error(f"[SYSTEM_CONFIG] Erros no serializer: {serializer.errors}")
                return Response(serializer.errors, status=400)
                
        except Exception as e:
            logger.error(f"Erro ao atualizar configurações do sistema: {e}", exc_info=True)
            return Response({'error': str(e)}, status=500)


def _get_system_config_singleton():
    config = SystemConfig.objects.filter(key='system_config').first()
    if not config:
        config = SystemConfig.objects.first()
    if not config:
        config = SystemConfig.objects.create(
            key='system_config',
            value='{}',
            description='Configurações gerais do sistema',
            is_active=True
        )
    return config


class BillingWhatsAppEmbeddedSignupFinishView(APIView):
    """
    Finaliza o Embedded Signup para o canal de cobrança exclusivo do superadmin.
    Persiste token/waba/phone_number_id diretamente em SystemConfig.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.user.user_type != 'superadmin':
            return Response({'success': False, 'error': 'Acesso negado'}, status=403)

        from integrations.embedded_signup_finish import exchange_code_for_token, fetch_phone_numbers_from_waba

        waba_id = request.data.get('waba_id')
        code = request.data.get('code')
        if not waba_id or not code:
            return Response({'success': False, 'error': 'waba_id e code são obrigatórios'}, status=400)

        access_token = exchange_code_for_token(code)
        if not access_token:
            return Response({'success': False, 'error': 'Falha na troca de token da Meta'}, status=400)

        phone_data = fetch_phone_numbers_from_waba(waba_id, access_token)
        if not phone_data:
            return Response({'success': False, 'error': 'Não foi possível obter phone_number_id do WABA'}, status=400)

        config = _get_system_config_singleton()
        config.billing_whatsapp_token = access_token
        config.billing_whatsapp_waba_id = waba_id
        config.billing_whatsapp_phone_number_id = phone_data.get('phone_number_id')
        config.billing_channel_enabled = True
        config.save(update_fields=[
            'billing_whatsapp_token',
            'billing_whatsapp_waba_id',
            'billing_whatsapp_phone_number_id',
            'billing_channel_enabled',
        ])

        return Response({
            'success': True,
            'billing': {
                'waba_id': config.billing_whatsapp_waba_id,
                'phone_number_id': config.billing_whatsapp_phone_number_id,
                'display_phone_number': phone_data.get('display_phone_number', ''),
                'verified_name': phone_data.get('verified_name', ''),
            }
        })


class BillingWhatsAppTemplatesView(APIView):
    """
    Lista e cria templates no canal de cobrança exclusivo do superadmin.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_billing_proxy(self):
        config = _get_system_config_singleton()
        return config, SimpleNamespace(
            token=config.billing_whatsapp_token,
            waba_id=config.billing_whatsapp_waba_id
        )

    def get(self, request):
        if request.user.user_type != 'superadmin':
            return Response({'success': False, 'error': 'Acesso negado'}, status=403)

        from integrations.whatsapp_templates import list_message_templates
        config, proxy = self._get_billing_proxy()
        if not config.billing_whatsapp_token or not config.billing_whatsapp_waba_id:
            return Response({'success': False, 'error': 'Canal de cobrança não conectado na Meta'}, status=400)

        ok, templates, error = list_message_templates(proxy)
        if not ok:
            return Response({'success': False, 'error': error or 'Erro ao listar templates'}, status=400)
        return Response({'success': True, 'templates': templates or []})

    def post(self, request):
        if request.user.user_type != 'superadmin':
            return Response({'success': False, 'error': 'Acesso negado'}, status=403)

        from integrations.whatsapp_templates import create_message_template
        config, proxy = self._get_billing_proxy()
        if not config.billing_whatsapp_token or not config.billing_whatsapp_waba_id:
            return Response({'success': False, 'error': 'Canal de cobrança não conectado na Meta'}, status=400)

        name = request.data.get('name')
        category = request.data.get('category', 'UTILITY')
        language = request.data.get('language', 'pt_BR')
        parameter_format = request.data.get('parameter_format', 'positional')
        components = request.data.get('components')
        body_text = request.data.get('body_text')

        if not name:
            return Response({'success': False, 'error': 'name é obrigatório'}, status=400)

        # Compatibilidade: se não vier components, montar mínimo com body_text
        if not components:
            if not body_text:
                return Response({'success': False, 'error': 'body_text é obrigatório quando components não é enviado'}, status=400)
            components = [{"type": "BODY", "text": body_text}]

        if not isinstance(components, list) or not components:
            return Response({'success': False, 'error': 'components deve ser uma lista não vazia'}, status=400)

        ok, template, error = create_message_template(
            canal=proxy,
            name=name,
            category=category,
            language=language,
            components=components,
            parameter_format=parameter_format,
        )
        if not ok:
            return Response({'success': False, 'error': error or 'Erro ao criar template'}, status=400)
        return Response({'success': True, 'template': template}, status=201)


class BillingWhatsAppTemplateDeleteView(APIView):
    """
    Remove template no canal de cobrança exclusivo do superadmin.
    """
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, template_id=None):
        if request.user.user_type != 'superadmin':
            return Response({'success': False, 'error': 'Acesso negado'}, status=403)

        from integrations.whatsapp_templates import delete_message_template
        config = _get_system_config_singleton()
        proxy = SimpleNamespace(
            token=config.billing_whatsapp_token,
            waba_id=config.billing_whatsapp_waba_id
        )
        if not proxy.token or not proxy.waba_id:
            return Response({'success': False, 'error': 'Canal de cobrança não conectado na Meta'}, status=400)
        if not template_id:
            return Response({'success': False, 'error': 'template_id é obrigatório'}, status=400)

        ok, error = delete_message_template(proxy, template_id)
        if not ok:
            return Response({'success': False, 'error': error or 'Erro ao deletar template'}, status=400)
        return Response({'success': True})

class ProvedorViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar provedores com isolamento por provedor
    """
    queryset = Provedor.objects.all()
    serializer_class = ProvedorSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Verificação de segurança: garantir que usuário está autenticado
        if not user.is_authenticated:
            return Provedor.objects.none()
        
        # Verificação segura de user_type
        user_type = getattr(user, 'user_type', None)
        
        # Superadmin vê todos os provedores
        if user_type == 'superadmin':
            queryset = Provedor.objects.all()
        else:
            # Outros usuários veem apenas seus provedores
            queryset = Provedor.objects.filter(admins=user)
        
        # Filtrar por nome, slug ou domínio se fornecido
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(nome__icontains=search) |
                Q(site_oficial__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        user = self.request.user
        # Verificação de segurança
        if not user.is_authenticated:
            raise PermissionDenied('Usuário não autenticado')
        user_type = getattr(user, 'user_type', None)
        if user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode criar provedores')
            
        provedor = serializer.save()
        
        # Setup Automático Asaas se houver CPF/CNPJ
        if provedor.cpf_cnpj:
            try:
                from integrations.asaas_service import AsaasService
                asaas_service = AsaasService()
                logger.info(f"[AsaasAuto] Iniciando setup automático para {provedor.nome}")
                
                # 1. Sincronizar Cliente
                from django.forms.models import model_to_dict
                provider_data = model_to_dict(provedor)
                res_customer = asaas_service.create_customer(provider_data)
                
                if res_customer.get('success'):
                    provedor.asaas_customer_id = res_customer.get('customer_id')
                    provedor.save()
                    
                    # Desativação granular se configurado
                    if provedor.notification_disabled:
                        asaas_service.bulk_disable_notifications(provedor.asaas_customer_id)
                    
                    # 2. Criar Assinatura se houver valor
                    if provedor.subscription_value and provedor.subscription_value > 0 and provedor.subscription_next_due_date:
                        sub_data = {
                            "customer": provedor.asaas_customer_id,
                            "billingType": provedor.subscription_billing_type or "BOLETO",
                            "value": float(provedor.subscription_value),
                            "nextDueDate": provedor.subscription_next_due_date.isoformat(),
                            "cycle": provedor.subscription_cycle or "MONTHLY",
                            "description": f"Assinatura Nio Hub - {provedor.nome}",
                            "externalReference": f"sub_provider_{provedor.id}",
                            "notificationDisabled": provedor.notification_disabled
                        }
                        res_sub = asaas_service.create_subscription(sub_data)
                        if res_sub.get('success'):
                            provedor.asaas_subscription_id = res_sub.get('subscription_id')
                            provedor.save()
                            logger.info(f"[AsaasAuto] Assinatura criada: {provedor.asaas_subscription_id}")
            except Exception as e:
                logger.error(f"[AsaasAuto] Falha no setup automático para provedor {provedor.id}: {str(e)}")
    
    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()
        
        # Superadmin pode atualizar tudo
        if user.user_type == 'superadmin':
            serializer.save()
            return
        
        # Admins do provedor podem atualizar todos os campos do provedor
        # Verificar se o usuário é admin deste provedor
        if not instance.admins.filter(id=user.id).exists():
            raise PermissionDenied('Você não tem permissão para atualizar este provedor')
        
        # Campos que admins NÃO podem atualizar (apenas superadmin)
        # Apenas campos críticos de segurança e administração são restritos
        restricted_fields = {
            'admins',  # Gerenciamento de admins (apenas superadmin)
            'is_active'  # Ativação/desativação do provedor (apenas superadmin)
        }
        # Admins podem atualizar TODOS os outros campos, incluindo:
        # - Dados básicos (nome, site_oficial, endereco)
        # - Configurações de IA (nome_agente_ia, estilo_personalidade, personalidade, modo_falar, informacoes_extras)
        # - Configurações de integração (SGP, WhatsApp)
        # - Outras configurações do provedor
        
        # Verificar se está tentando atualizar campos restritos
        data = serializer.validated_data
        for field in restricted_fields:
            if field in data:
                # Verificar se o valor realmente mudou
                if hasattr(instance, field):
                    old_value = getattr(instance, field)
                    new_value = data.get(field)
                    if old_value != new_value:
                        raise PermissionDenied(f'Apenas superadmin pode atualizar o campo "{field}".')
        
        # Permitir atualização de todos os outros campos
        serializer.save()
    
    def perform_destroy(self, instance):
        user = self.request.user
        if user.user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode deletar provedores')
        instance.delete()
    
    @action(detail=True, methods=['post'], url_path='limpar_banco_dados')
    def limpar_banco_dados(self, request, pk=None):
        """
        Limpa todas as conversas, mensagens e contatos deste provedor
        ATENÇÃO: Operação irreversível!
        
        IMPORTANTE: Usuários do provedor NÃO são removidos.
        Apenas dados operacionais (conversas, mensagens, contatos, etc.) são deletados.
        """
        from django.db import transaction
        from conversations.models import (
            Message, Conversation, Contact, Inbox, Team, TeamMember,
            InternalChatRoom, InternalChatParticipant, InternalChatMessage,
            InternalChatMessageRead, InternalChatReaction,
            PrivateMessage, PrivateMessageReaction,
            RecoveryAttempt, CSATFeedback, CSATRequest
        )
        from core.redis_memory_service import redis_memory_service
        
        user = request.user
        provedor = self.get_object()
        
        # Verificar permissão (apenas superadmin)
        if user.user_type != 'superadmin':
            return Response(
                {'error': 'Apenas superadmin pode executar limpeza de banco de dados'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            with transaction.atomic():
                # Contadores
                counts = {}
                
                # 1. Limpar mensagens privadas relacionadas ao provedor
                # (filtrar por usuários que são admins do provedor)
                provedor_admins = provedor.admins.all()
                private_reactions = PrivateMessageReaction.objects.filter(
                    user__in=provedor_admins
                )
                counts['private_reactions'] = private_reactions.count()
                private_reactions.delete()
                
                private_messages = PrivateMessage.objects.filter(
                    sender__in=provedor_admins
                ) | PrivateMessage.objects.filter(
                    recipient__in=provedor_admins
                )
                counts['private_messages'] = private_messages.count()
                private_messages.delete()
                
                # 2. Limpar chat interno relacionado ao provedor
                internal_reactions = InternalChatReaction.objects.filter(
                    user__in=provedor_admins
                )
                counts['internal_reactions'] = internal_reactions.count()
                internal_reactions.delete()
                
                internal_reads = InternalChatMessageRead.objects.filter(
                    user__in=provedor_admins
                )
                counts['internal_reads'] = internal_reads.count()
                internal_reads.delete()
                
                internal_messages = InternalChatMessage.objects.filter(
                    sender__in=provedor_admins
                )
                counts['internal_messages'] = internal_messages.count()
                internal_messages.delete()
                
                internal_participants = InternalChatParticipant.objects.filter(
                    user__in=provedor_admins
                )
                counts['internal_participants'] = internal_participants.count()
                internal_participants.delete()
                
                internal_rooms = InternalChatRoom.objects.filter(
                    provedor=provedor
                )
                counts['internal_rooms'] = internal_rooms.count()
                internal_rooms.delete()
                
                # 3. Limpar tentativas de recuperação
                recovery_attempts = RecoveryAttempt.objects.filter(
                    conversation__inbox__provedor=provedor
                )
                counts['recovery_attempts'] = recovery_attempts.count()
                recovery_attempts.delete()
                
                # 4. Limpar CSAT
                csat_feedbacks = CSATFeedback.objects.filter(provedor=provedor)
                counts['csat_feedbacks'] = csat_feedbacks.count()
                csat_feedbacks.delete()
                
                csat_requests = CSATRequest.objects.filter(
                    conversation__inbox__provedor=provedor
                )
                counts['csat_requests'] = csat_requests.count()
                csat_requests.delete()
                
                # 5. Limpar mensagens
                messages = Message.objects.filter(conversation__inbox__provedor=provedor)
                counts['messages'] = messages.count()
                messages.delete()
                
                # 6. Limpar conversas
                conversations = Conversation.objects.filter(inbox__provedor=provedor)
                counts['conversations'] = conversations.count()
                conversations.delete()
                
                # 7. Limpar contatos (Contact tem provedor diretamente, não inbox__provedor)
                contacts = Contact.objects.filter(provedor=provedor)
                counts['contacts'] = contacts.count()
                contacts.delete()
                
                # 8. Limpar equipes
                team_members = TeamMember.objects.filter(team__provedor=provedor)
                counts['team_members'] = team_members.count()
                team_members.delete()
                
                teams = Team.objects.filter(provedor=provedor)
                counts['teams'] = teams.count()
                teams.delete()
                
                # 9. Limpar inboxes (exceto o provedor em si)
                inboxes = Inbox.objects.filter(provedor=provedor)
                counts['inboxes'] = inboxes.count()
                inboxes.delete()
                
                # 9.5. Limpar conversas órfãs/inconsistentes (que podem aparecer na auditoria)
                # Conversas sem inbox válido, sem contact válido, ou com referências quebradas
                # Primeiro, buscar todas as conversas do provedor que são órfãs
                all_provedor_conversations = Conversation.objects.filter(
                    Q(inbox__provedor=provedor) | Q(contact__provedor=provedor)
                )
                
                # Identificar conversas órfãs (sem inbox, sem contact, ou inbox sem provedor)
                orphaned_conversations = all_provedor_conversations.filter(
                    Q(inbox__isnull=True) | 
                    Q(contact__isnull=True) |
                    Q(inbox__provedor__isnull=True)
                )
                counts['orphaned_conversations'] = orphaned_conversations.count()
                
                # Remover mensagens dessas conversas órfãs primeiro
                orphaned_messages = Message.objects.filter(conversation__in=orphaned_conversations)
                counts['orphaned_messages'] = orphaned_messages.count()
                orphaned_messages.delete()
                
                # Depois remover as conversas órfãs
                orphaned_conversations.delete()
                
                # Limpar AuditLogs órfãos (sem conversation válida) do provedor
                from core.models import AuditLog
                # Converter IDs de conversa para string (pois conversation_id no AuditLog é CharField)
                all_conversation_ids = [str(id) for id in Conversation.objects.values_list('id', flat=True)]
                orphaned_audit_logs = AuditLog.objects.filter(
                    conversation_id__isnull=False,
                    provedor=provedor
                ).exclude(
                    conversation_id__in=all_conversation_ids
                )
                counts['orphaned_audit_logs'] = orphaned_audit_logs.count()
                orphaned_audit_logs.delete()
                
                # 10. Limpar Redis do provedor
                redis_cleared = False
                try:
                    redis_cleared = redis_memory_service.clear_provider_data(provedor.id)
                except Exception as redis_error:
                    logger.warning(f"Erro ao limpar Redis: {redis_error}")
                
                # NOTA: Usuários do provedor (provedor.admins) NÃO são removidos
                # Apenas dados operacionais são deletados acima
                
                total_deleted = sum(counts.values())
                
                return Response({
                    'success': True,
                    'message': f'Limpeza concluída com sucesso! {total_deleted} registros removidos.',
                    'counts': counts,
                    'redis_cleared': redis_cleared,
                    'total_deleted': total_deleted
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Erro ao limpar banco de dados do provedor {provedor.id}: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Erro ao executar limpeza: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='limpar_redis')
    def limpar_redis(self, request, pk=None):
        """
        Limpa todas as chaves de cache e memória Redis deste provedor
        """
        from core.redis_memory_service import redis_memory_service
        
        user = request.user
        provedor = self.get_object()
        
        # Verificar permissão (apenas superadmin)
        if user.user_type != 'superadmin':
            return Response(
                {'error': 'Apenas superadmin pode executar limpeza de Redis'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Obter estatísticas antes da limpeza
            stats_before = redis_memory_service.get_provider_stats(provedor.id)
            
            # Limpar dados
            success = redis_memory_service.clear_provider_data(provedor.id)
            
            if success:
                # Obter estatísticas depois da limpeza
                stats_after = redis_memory_service.get_provider_stats(provedor.id)
                
                return Response({
                    'success': True,
                    'message': f'Redis do provedor {provedor.nome} limpo com sucesso!',
                    'stats_before': {
                        'total_keys': stats_before.get('total_keys', 0) if stats_before else 0,
                        'key_types': stats_before.get('key_types', {}) if stats_before else {}
                    },
                    'stats_after': {
                        'total_keys': stats_after.get('total_keys', 0) if stats_after else 0,
                        'key_types': stats_after.get('key_types', {}) if stats_after else {}
                    }
                }, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'error': 'Erro ao limpar dados do Redis'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Exception as e:
            logger.error(f"Erro ao limpar Redis do provedor {provedor.id}: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Erro ao executar limpeza de Redis: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='limpar_auditlog')
    def limpar_auditlog(self, request, pk=None):
        """
        Limpa todos os logs de auditoria (core_auditlog) deste provedor
        ATENÇÃO: Operação irreversível!
        """
        from core.models import AuditLog
        
        user = request.user
        provedor = self.get_object()
        
        # Verificar permissão (apenas superadmin)
        if user.user_type != 'superadmin':
            return Response(
                {'error': 'Apenas superadmin pode executar limpeza de logs de auditoria'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # Contar logs antes da limpeza
            logs_before = AuditLog.objects.filter(provedor=provedor).count()
            
            # Limpar todos os logs de auditoria do provedor
            deleted_count, _ = AuditLog.objects.filter(provedor=provedor).delete()
            
            # Verificar se foi limpo corretamente
            logs_after = AuditLog.objects.filter(provedor=provedor).count()
            
            return Response({
                'success': True,
                'message': f'Logs de auditoria do provedor {provedor.nome} limpos com sucesso! {deleted_count} registros removidos.',
                'logs_before': logs_before,
                'logs_after': logs_after,
                'deleted_count': deleted_count
            }, status=status.HTTP_200_OK)
                
        except Exception as e:
            logger.error(f"Erro ao limpar logs de auditoria do provedor {provedor.id}: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Erro ao executar limpeza de logs de auditoria: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='sync_asaas')
    def sync_asaas(self, request, pk=None):
        """
        Sincroniza os dados do provedor com o Asaas criando um novo cliente.
        Agora aceita dados no request para atualizar o provedor antes de sincronizar.
        """
        user = request.user
        provedor = self.get_object()
        
        # Verificar permissão (apenas superadmin)
        if getattr(user, 'user_type', None) != 'superadmin':
            return Response(
                {'error': 'Apenas superadmin pode sincronizar com Asaas'},
                status=status.HTTP_403_FORBIDDEN
            )
            
        try:
            # 1. Atualizar provedor com dados enviados (se houver)
            # Isso garante que campos como notification_disabled sejam salvos antes da sincronização
            data = request.data
            if data:
                logger.info(f"[AsaasSync] Atualizando dados locais do provedor {provedor.id} antes de sincronizar")
                if 'nome' in data: provedor.nome = data.get('nome')
                if 'cpf_cnpj' in data: provedor.cpf_cnpj = data.get('cpf_cnpj')
                if 'email_contato' in data: provedor.email_contato = data.get('email_contato')
                if 'mobile_phone' in data: provedor.mobile_phone = data.get('mobile_phone')
                if 'postal_code' in data: provedor.postal_code = data.get('postal_code')
                if 'endereco' in data: provedor.endereco = data.get('endereco')
                if 'address_number' in data: provedor.address_number = data.get('address_number')
                if 'notification_disabled' in data: 
                    provedor.notification_disabled = data.get('notification_disabled')
                if 'foreign_customer' in data:
                    provedor.foreign_customer = data.get('foreign_customer')
                if 'company' in data: provedor.company = data.get('company')
                if 'group_name' in data: provedor.group_name = data.get('group_name')
                if 'additional_emails' in data: provedor.additional_emails = data.get('additional_emails')
                
                provedor.save()

            # 2. Validar campos obrigatórios
            if not provedor.cpf_cnpj or not provedor.nome:
                return Response(
                    {'error': 'Nome e CPF/CNPJ são obrigatórios para sincronizar com Asaas'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            asaas_service = AsaasService()
            
            # Preparar dados para o serviço
            from django.forms.models import model_to_dict
            provider_data = model_to_dict(provedor)
            
            logger.info(f"[AsaasSync] Enviando para Asaas: notificationDisabled={provider_data.get('notification_disabled')}")
            
            # 3. Executar a criação do cliente no Asaas
            result = asaas_service.create_customer(provider_data)
            
            if result.get('success'):
                # Salvar o ID retornado
                provedor.asaas_customer_id = result.get('customer_id')
                provedor.save()
                
                # Se notificações devem ser desativadas, fazer a desativação granular
                if provedor.notification_disabled:
                    logger.info(f"[AsaasSync] Desativando notificações granulares para o cliente {provedor.asaas_customer_id}")
                    asaas_service.bulk_disable_notifications(provedor.asaas_customer_id)
                
                return Response({
                    'success': True,
                    'message': 'Provedor sincronizado com sucesso no Asaas!',
                    'customer_id': provedor.asaas_customer_id,
                    'data': result.get('data')
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'error': result.get('error')
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Erro ao sincronizar provedor {provedor.id} com Asaas: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Erro na sincronização: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='create_subscription')
    def create_subscription(self, request, pk=None):
        """
        Cria uma assinatura no Asaas para o provedor
        """
        user = request.user
        provedor = self.get_object()
        
        # Verificar permissão (apenas superadmin)
        if getattr(user, 'user_type', None) != 'superadmin':
            return Response(
                {'error': 'Apenas superadmin pode gerenciar assinaturas'},
                status=status.HTTP_403_FORBIDDEN
            )
            
        if not provedor.asaas_customer_id:
            return Response(
                {'error': 'Provedor não sincronizado com Asaas. Sincronize o cliente primeiro.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Dados vindos do frontend
            value = request.data.get('value')
            next_due_date = request.data.get('nextDueDate')
            cycle = request.data.get('cycle', 'MONTHLY')
            billing_type = request.data.get('billingType', 'BOLETO')
            description = f"Assinatura Nio Hub - {provedor.nome}"

            if not value or not next_due_date:
                return Response(
                    {'error': 'Valor e Data de Vencimento são obrigatórios'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            asaas_service = AsaasService()
            
            subscription_data = {
                "customer": provedor.asaas_customer_id,
                "billingType": billing_type,
                "value": value,
                "nextDueDate": next_due_date,
                "cycle": cycle,
                "description": description,
                "externalReference": f"sub_provider_{provedor.id}",
                "notificationDisabled": provedor.notification_disabled
            }

            result = asaas_service.create_subscription(subscription_data)
            
            if result.get('success'):
                # Salvar detalhes no modelo
                provedor.asaas_subscription_id = result.get('subscription_id')
                provedor.subscription_value = value
                provedor.subscription_cycle = cycle
                provedor.subscription_billing_type = billing_type
                provedor.subscription_status = result.get('data', {}).get('status')
                provedor.save()
                
                return Response({
                    'success': True,
                    'message': 'Assinatura criada com sucesso!',
                    'subscription_id': provedor.asaas_subscription_id,
                    'data': result.get('data')
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'error': result.get('error')
                }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Erro ao criar assinatura para provedor {provedor.id}: {str(e)}", exc_info=True)
            return Response(
                {'error': f'Erro na criação da assinatura: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['get'])
    def subscription_payments(self, request, pk=None):
        """
        Retorna a lista de cobranças vinculadas à assinatura do provedor
        """
        user = request.user
        provedor = self.get_object()
        
        if getattr(user, 'user_type', None) != 'superadmin':
            return Response({'error': 'Acesso negado'}, status=403)
            
        if not provedor.asaas_subscription_id:
            return Response({'success': True, 'data': []})
            
        asaas_service = AsaasService()
        result = asaas_service.list_payments(subscription_id=provedor.asaas_subscription_id)
        
        if result.get('success'):
            # Formatar dados para o frontend
            payments = []
            for p in result.get('data', []):
                payments.append({
                    'id': p.get('id'),
                    'dueDate': p.get('dueDate'),
                    'value': p.get('value'),
                    'netValue': p.get('netValue'),
                    'status': p.get('status'),
                    'billingType': p.get('billingType'),
                    'confirmedDate': p.get('confirmedDate'),
                    'paymentDate': p.get('paymentDate'),
                    'invoiceUrl': p.get('invoiceUrl'),
                    'bankSlipUrl': p.get('bankSlipUrl')
                })
            return Response({'success': True, 'data': payments})
        
        return Response({'error': result.get('error')}, status=400)

    @action(detail=True, methods=['post'], url_path='verify_asaas')
    def verify_asaas(self, request, pk=None):
        """
        Verifica se o cliente e a assinatura ainda existem no Asaas.
        Se não existirem (404), limpa os campos locais.
        """
        user = request.user
        provedor = self.get_object()
        
        if getattr(user, 'user_type', None) != 'superadmin':
            return Response({'error': 'Acesso negado'}, status=403)
            
        asaas_service = AsaasService()
        changes = False
        status_info = {"customer": "not_checked", "subscription": "not_checked", "billing": "not_checked"}

        # 1. Verificar Cliente
        if provedor.asaas_customer_id:
            res = asaas_service.get_customer(provedor.asaas_customer_id)
            if not res.get('success') and res.get('status_code') == 404:
                logger.warning(f"[AsaasVerify] Cliente {provedor.asaas_customer_id} não encontrado. Limpando IDs.")
                provedor.asaas_customer_id = None
                provedor.asaas_subscription_id = None
                status_info["customer"] = "deleted_locally"
                changes = True
            elif res.get('success'):
                status_info["customer"] = "active"
            else:
                status_info["customer"] = f"error: {res.get('error')}"

        # 2. Verificar Assinatura (se o cliente ainda for válido)
        if provedor.asaas_customer_id and provedor.asaas_subscription_id:
            res = asaas_service.get_subscription(provedor.asaas_subscription_id)
            if not res.get('success'):
                # Assumindo que falha de busca de assinatura individual pode ser 404
                # Infelizmente asaas_service.get_subscription não retorna status_code ainda, mas podemos inferir pelo erro
                error_msg = res.get('error', '').lower()
                if 'not_found' in error_msg or '404' in error_msg or 'não encontrada' in error_msg:
                    logger.warning(f"[AsaasVerify] Assinatura {provedor.asaas_subscription_id} não encontrada. Limpando.")
                    provedor.asaas_subscription_id = None
                    status_info["subscription"] = "deleted_locally"
                    changes = True
                else:
                    status_info["subscription"] = f"error: {res.get('error')}"
            else:
                # Atualizar status local se necessário
                new_status = res.get('data', {}).get('status')
                if provedor.subscription_status != new_status:
                    provedor.subscription_status = new_status
                    changes = True
                status_info["subscription"] = "active"

        # 3. Verificar inadimplência (OVERDUE) e aplicar bloqueio/desbloqueio local
        from core.asaas_provedor_block import apply_subscription_overdue_block_for_provedor

        block_res = apply_subscription_overdue_block_for_provedor(provedor, asaas_service)
        status_info["billing"] = block_res.get("billing", "not_checked")
        if block_res.get("changes"):
            changes = True

        if changes:
            provedor.save()
            
        return Response({
            "success": True,
            "status_info": status_info,
            "asaas_customer_id": provedor.asaas_customer_id,
            "asaas_subscription_id": provedor.asaas_subscription_id,
            "subscription_status": provedor.subscription_status
        })

    @action(detail=False, methods=['get'])
    def status_pagamento(self, request):
        """
        Verifica o status de pagamento do provedor do usuário atual
        e retorna dados de cobrança se estiver bloqueado.
        """
        user = request.user
        
        # Encontrar provedor do usuário (ou o que ele administra)
        provedor = None
        if hasattr(user, 'provedores_admin'):
            provedor = user.provedores_admin.first()
            
        if not provedor:
            return Response({'blocked': False})

        from core.asaas_provedor_block import (
            get_auto_block_settings,
            is_asaas_auto_inadimplencia_reason,
            list_subscription_overdue_payments,
            payment_is_blocking_overdue,
        )

        enabled, min_days_late = get_auto_block_settings()
        if not enabled:
            return Response({'blocked': False})

        asaas_service = AsaasService()
        ok, overdue_payments, _err = list_subscription_overdue_payments(provedor, asaas_service)
        if not ok or not overdue_payments:
            return Response({'blocked': False})

        blocking_overdues = [
            p
            for p in overdue_payments
            if payment_is_blocking_overdue(p.get('dueDate'), min_days_late)
        ]
        if not blocking_overdues:
            return Response({'blocked': False})

        latest_overdue = blocking_overdues[0]
        payment_id = latest_overdue.get('id')
        qr_result = asaas_service.get_payment_pix_qr_code(payment_id)

        reason_text = provedor.block_reason
        if not is_asaas_auto_inadimplencia_reason(reason_text):
            reason_text = (
                'Pagamento pendente no Asaas. Quite a fatura para continuar usando o sistema.'
            )

        return Response(
            {
                'blocked': True,
                'reason': reason_text,
                'payment': {
                    'id': payment_id,
                    'value': latest_overdue.get('value'),
                    'dueDate': latest_overdue.get('dueDate'),
                    'invoiceUrl': latest_overdue.get('invoiceUrl'),
                    'description': latest_overdue.get('description'),
                },
                'pix': qr_result.get('data') if qr_result.get('success') else None,
            }
        )

class CompanyViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar empresas (companies) com isolamento por provedor
    """
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Verificação de segurança: garantir que usuário está autenticado
        if not user.is_authenticated:
            return Company.objects.none()
        
        # Verificação segura de user_type
        user_type = getattr(user, 'user_type', None)
        
        # Superadmin vê todas as empresas
        if user_type == 'superadmin':
            queryset = Company.objects.all()
        else:
            # Outros usuários veem apenas empresas relacionadas aos seus provedores
            provedores = Provedor.objects.filter(admins=user)
            if provedores.exists():
                # Filtrar empresas relacionadas aos provedores do usuário
                queryset = Company.objects.filter(
                    companyuser__user__provedores_admin__in=provedores
                ).distinct()
            else:
                queryset = Company.objects.none()
        
        # Filtrar por nome ou domínio se fornecido
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(domain__icontains=search)
            )
        
        return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        user = self.request.user
        # Verificação de segurança
        if not user.is_authenticated:
            raise PermissionDenied('Usuário não autenticado')
        user_type = getattr(user, 'user_type', None)
        if user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode criar empresas')
        serializer.save()
    
    def perform_update(self, serializer):
        user = self.request.user
        # Verificação de segurança
        if not user.is_authenticated:
            raise PermissionDenied('Usuário não autenticado')
        user_type = getattr(user, 'user_type', None)
        if user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode atualizar empresas')
        serializer.save()
    
    def perform_destroy(self, instance):
        user = self.request.user
        # Verificação de segurança
        if not user.is_authenticated:
            raise PermissionDenied('Usuário não autenticado')
        user_type = getattr(user, 'user_type', None)
        if user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode deletar empresas')
        instance.delete()

class MensagemSistemaViewSet(viewsets.ModelViewSet):
    """
    ViewSet para gerenciar mensagens do sistema para provedores
    """
    queryset = MensagemSistema.objects.all()
    serializer_class = MensagemSistemaSerializer
    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        
        # Superadmin vê todas as mensagens
        if user.user_type == 'superadmin':
            return MensagemSistema.objects.all().order_by('-created_at')
        
        # Buscar provedores do usuário
        provedores = Provedor.objects.filter(admins=user)
        if not provedores.exists():
            return MensagemSistema.objects.none()
        
        # IDs dos provedores do usuário
        provedor_ids = list(provedores.values_list('id', flat=True))
        
        # Verificar vendor do banco de dados
        from django.db import connection
        from django.db.models import Q
        
        if connection.vendor == 'sqlite':
            # No SQLite, buscar todas as mensagens e filtrar manualmente em Python
            todas_mensagens = MensagemSistema.objects.all().order_by('-created_at')
            mensagens_filtradas_ids = []
            
            for mensagem in todas_mensagens:
                mensagem_provedores = mensagem.provedores if isinstance(mensagem.provedores, list) else []
                # Converter para int se necessário
                mensagem_provedores_int = []
                for pid in mensagem_provedores:
                    try:
                        mensagem_provedores_int.append(int(pid))
                    except (ValueError, TypeError):
                        pass
                
                # Verificar acesso e visibilidade
                is_visible = True
                if user.user_type == 'agent' and not mensagem.visivel_para_agentes:
                    is_visible = False
                    
                if is_visible and (any(pid in mensagem_provedores_int for pid in provedor_ids) or mensagem.provedor in provedores):
                    mensagens_filtradas_ids.append(mensagem.id)
            
            return MensagemSistema.objects.filter(id__in=mensagens_filtradas_ids).order_by('-created_at')
        else:
            # No PostgreSQL, podemos usar contains
            q_objects = Q()
            for provedor_id in provedor_ids:
                q_objects |= Q(provedores__contains=[provedor_id])
            
            queryset = MensagemSistema.objects.filter(
                q_objects | Q(provedor__in=provedores)
            ).distinct()
            
            # Filtro adicional para agentes
            if user.user_type == 'agent':
                queryset = queryset.filter(visivel_para_agentes=True)
                
            return queryset.order_by('-created_at')
    
    def perform_create(self, serializer):
        user = self.request.user
        if user.user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode criar mensagens do sistema')
        
        # Obter campos da requisição
        provedores_ids = self.request.data.get('provedores', [])
        visivel_para_agentes = self.request.data.get('visivel_para_agentes', True)
        
        # Garantir que são inteiros para consistência e segurança
        clean_provedores_ids = []
        for pid in provedores_ids:
            try:
                clean_provedores_ids.append(int(pid))
            except (ValueError, TypeError):
                continue

        # Salvar a mensagem com os dados limpos
        mensagem = serializer.save(
            provedores=clean_provedores_ids,
            provedores_count=len(clean_provedores_ids),
            visivel_para_agentes=visivel_para_agentes
        )
        
        logger.info(f"[MENSAGEM_SISTEMA] Nova mensagem criada ID: {mensagem.id} para {len(clean_provedores_ids)} provedores")
        
        # Notificar via WebSocket todos os provedores destinatários
        self._notify_new_system_message(mensagem, clean_provedores_ids)
    
    def perform_update(self, serializer):
        user = self.request.user
        if user.user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode atualizar mensagens do sistema')
        
        # Salvar dados da mensagem
        mensagem = serializer.save()
        
        # Se provedores foi fornecido, atualizar o campo provedores de forma limpa
        provedores_ids = self.request.data.get('provedores', None)
        if provedores_ids is not None:
            clean_ids = []
            for pid in provedores_ids:
                try:
                    clean_ids.append(int(pid))
                except (ValueError, TypeError):
                    continue
            mensagem.provedores = clean_ids
            mensagem.provedores_count = len(clean_ids)
        
        # Atualizar visibilidade se fornecida
        if 'visivel_para_agentes' in self.request.data:
            mensagem.visivel_para_agentes = self.request.data.get('visivel_para_agentes')
            
        mensagem.save()
        logger.info(f"[MENSAGEM_SISTEMA] Mensagem {mensagem.id} atualizada com {len(clean_ids)} provedores")
    
    def perform_destroy(self, instance):
        user = self.request.user
        if user.user_type != 'superadmin':
            raise PermissionDenied('Apenas superadmin pode deletar mensagens do sistema')
        instance.delete()
    
    @action(detail=False, methods=['get'], url_path='minhas_mensagens')
    def minhas_mensagens(self, request):
        """Retorna mensagens do sistema para os provedores do usuário logado"""
        user = request.user
        
        # Buscar provedores do usuário
        provedores = Provedor.objects.filter(admins=user)
        if not provedores.exists():
            return Response([])
        
        # IDs dos provedores do usuário
        provedor_ids = list(provedores.values_list('id', flat=True))
        
        # Buscar TODAS as mensagens e filtrar manualmente no Python
        # Isso é necessário porque SQLite não suporta contains lookup em JSONField
        from django.db import connection
        if connection.vendor == 'sqlite':
            # No SQLite, buscar todas as mensagens e filtrar manualmente
            todas_mensagens = MensagemSistema.objects.all().order_by('-created_at')
        else:
            # No PostgreSQL, podemos usar contains
            q_objects = Q()
            for provedor_id in provedor_ids:
                q_objects |= Q(provedores__contains=[provedor_id])
            
            todas_mensagens = MensagemSistema.objects.filter(
                q_objects | Q(provedor__in=provedores)
            ).order_by('-created_at')
        
        # Filtrar manualmente no Python para garantir que funciona em todos os bancos
        mensagens_filtradas = []
        for mensagem in todas_mensagens:
            # Verificar se algum dos provedores do usuário está na lista de provedores da mensagem
            mensagem_provedores = mensagem.provedores if isinstance(mensagem.provedores, list) else []
            
            # Converter para int se necessário
            mensagem_provedores_int = []
            for pid in mensagem_provedores:
                try:
                    mensagem_provedores_int.append(int(pid))
                except (ValueError, TypeError):
                    pass
            
            # Verificar visibilidade para agentes
            if user.user_type == 'agent' and not mensagem.visivel_para_agentes:
                continue
                
            # Verificar se algum provedor do usuário está na lista
            if any(pid in mensagem_provedores_int for pid in provedor_ids) or mensagem.provedor in provedores:
                mensagens_filtradas.append(mensagem)
        
        serializer = self.get_serializer(mensagens_filtradas, many=True)
        return Response(serializer.data)
    
    def _notify_new_system_message(self, mensagem, provedores_ids):
        """Notifica via WebSocket todos os administradores dos provedores destinatários"""
        try:
            channel_layer = get_channel_layer()
            if not channel_layer:
                logger.warning("[MENSAGEM_SISTEMA] Channel layer não disponível para notificação")
                return
            
            # Serializar mensagem para envio
            from core.serializers import MensagemSistemaSerializer
            mensagem_data = MensagemSistemaSerializer(mensagem).data
            
            # Garantir que provedores_ids seja uma lista iterável
            if not isinstance(provedores_ids, list):
                provedores_ids = [provedores_ids] if provedores_ids else []

            # Notificar cada provedor destinatário
            for provedor_id in provedores_ids:
                try:
                    p_id = int(provedor_id)
                    # Buscar o provedor para obter os admins
                    provedor = Provedor.objects.filter(id=p_id).first()
                    if not provedor:
                        logger.warning(f"[MENSAGEM_SISTEMA] Provedor {p_id} não encontrado para envio de WS")
                        continue
                    
                    # 1. Notificar cada administrador individualmente nos seus grupos privados
                    admins = provedor.admins.all()
                    admin_ids = [a.id for a in admins]
                    logger.info(f"[MENSAGEM_SISTEMA] Notificando {len(admin_ids)} admins do provedor {p_id}: {admin_ids}")
                    
                    for admin in admins:
                        group_name = f'notifications_{admin.id}'
                        async_to_sync(channel_layer.group_send)(
                            group_name,
                            {
                                'type': 'send_notification',
                                'notification': {
                                    'type': 'system_message',
                                    'message': mensagem_data,
                                    'timestamp': timezone.now().isoformat()
                                }
                            }
                        )
                    
                    # 2. Também notificar o grupo geral do painel do provedor
                    group_name_painel = f'painel_{p_id}'
                    async_to_sync(channel_layer.group_send)(
                        group_name_painel,
                        {
                            'type': 'system_message',
                            'message': mensagem_data,
                            'timestamp': timezone.now().isoformat()
                        }
                    )
                    logger.info(f"[MENSAGEM_SISTEMA] WebSocket disparado com sucesso para provedor {p_id} ({admins.count()} admins notificados)")
                    
                except Exception as e:
                    logger.error(f"[MENSAGEM_SISTEMA] Erro ao notificar provedor {provedor_id}: {e}")
            
        except Exception as e:
            logger.error(f"[MENSAGEM_SISTEMA] Erro de alto nível na notificação de mensagem do sistema: {e}", exc_info=True)
    
    @action(detail=True, methods=['patch'], url_path='marcar-visualizada')
    def marcar_visualizada(self, request, pk=None):
        """Marca mensagem como visualizada pelo usuário atual"""
        try:
            # Obter pk do kwargs se não foi passado como parâmetro
            if pk is None:
                pk = self.kwargs.get('pk')
            
            # Buscar mensagem diretamente, sem usar get_queryset filtrado
            # Isso permite que qualquer usuário marque como visualizada se tiver acesso à mensagem
            try:
                mensagem = MensagemSistema.objects.get(pk=pk)
            except MensagemSistema.DoesNotExist:
                return Response({'error': 'Mensagem não encontrada'}, status=404)
            
            # Verificar se o usuário tem acesso à mensagem (é admin de algum dos provedores da mensagem)
            user = request.user
            user_provedores = Provedor.objects.filter(admins=user)
            user_provedor_ids = list(user_provedores.values_list('id', flat=True))
            
            # Verificar se a mensagem é para algum dos provedores do usuário
            mensagem_provedores = mensagem.provedores if isinstance(mensagem.provedores, list) else []
            mensagem_provedores_int = []
            for pid in mensagem_provedores:
                try:
                    mensagem_provedores_int.append(int(pid))
                except (ValueError, TypeError):
                    pass
            
            # Verificar acesso
            has_access = (
                any(pid in mensagem_provedores_int for pid in user_provedor_ids) or
                mensagem.provedor in user_provedores or
                user.user_type == 'superadmin'
            )
            
            if not has_access:
                return Response(
                    {'error': 'Você não tem permissão para marcar esta mensagem como visualizada'},
                    status=403
                )

            try:
                # Atualizar visualizações
                user_id = user.id
                visualizacoes = mensagem.visualizacoes or {}

                if str(user_id) not in visualizacoes:
                    visualizacoes[str(user_id)] = {
                        'user_id': user_id,
                        'user_name': user.username,
                        'visualized_at': timezone.now().isoformat()
                    }
                    mensagem.visualizacoes = visualizacoes
                    mensagem.visualizacoes_count = len(visualizacoes)
                    mensagem.save()

                return Response({
                    'success': True,
                    'message': 'Mensagem marcada como visualizada'
                })

            except Exception as e:
                logger.error(
                    f"Erro ao marcar mensagem como visualizada: {e}",
                    exc_info=True
                )
                return Response(
                    {'error': str(e)},
                    status=500
                )
        except Exception as e:
            logger.error(
                f"Erro geral ao processar marcação de visualizada: {e}",
                exc_info=True
            )
            return Response(
                {'error': str(e)},
                status=500
            )


@csrf_exempt
def facebook_callback(request):
    code = request.GET.get("code")
    state = request.GET.get("state")

    if not code:
        return JsonResponse(
            {"success": False, "error": "code não recebido"},
            status=400
        )

    return JsonResponse({
        "success": True,
        "message": "OAuth Meta recebido com sucesso",
        "state": state,
    })

class ChatbotFlowViewSet(viewsets.ModelViewSet):
    def get_serializer_class(self):
        from core.serializers import ChatbotFlowSerializer
        return ChatbotFlowSerializer
    
    queryset = ChatbotFlow.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = ChatbotFlow.objects.all()
        
        logger.info(f"[CHATBOT-FLOW] get_queryset - User: {user.username} (type: {user.user_type})")
        
        if user.user_type != 'superadmin':
            provedores = Provedor.objects.filter(admins=user)
            queryset = queryset.filter(provedor__in=provedores)
            logger.info(f"[CHATBOT-FLOW] Filtrado por provedores do admin: {[p.id for p in provedores]}")
            
        provedor_id = self.request.query_params.get('provedor')
        if provedor_id:
            queryset = queryset.filter(provedor_id=provedor_id)
        final_count = queryset.count()
        logger.info(f"[CHATBOT-FLOW] Fluxos encontrados: {final_count}")
        return queryset.order_by('-updated_at')

    def perform_create(self, serializer):
        logger.info(f"[CHATBOT-FLOW] Executando perform_create - Data: {serializer.validated_data.keys()}")
        if 'provedor' not in serializer.validated_data:
            provedor = self.request.user.provedores_admin.first()
            if provedor:
                logger.info(f"[CHATBOT-FLOW] Provedor automático selecionado: {provedor.id}")
                serializer.save(provedor=provedor)
            else:
                logger.warning("[CHATBOT-FLOW] Nenhum provedor encontrado para o usuário")
                serializer.save()
        else:
            logger.info(f"[CHATBOT-FLOW] Provedor recebido no request: {serializer.validated_data['provedor'].id}")
            serializer.save()

    def perform_update(self, serializer):
        logger.info(f"[CHATBOT-FLOW] Executando perform_update para ID {self.kwargs.get('pk')}")
        edges_received = serializer.validated_data.get('edges', [])
        nodes_received = serializer.validated_data.get('nodes', [])
        logger.info(f"[CHATBOT-FLOW] Nós recebidos: {len(nodes_received)}")
        logger.info(f"[CHATBOT-FLOW] Edges recebidas: {len(edges_received)}")
        for e in edges_received:
            logger.info(f"[CHATBOT-FLOW]   Edge: {e.get('source')} → {e.get('target')} | handle={e.get('sourceHandle')}")
        instance = serializer.save()
        logger.info(f"[CHATBOT-FLOW] Salvo com sucesso. Nodes no DB: {len(instance.nodes)}")

    @action(detail=True, methods=['get'])
    def export_flow(self, request, pk=None):
        """Exporta o fluxo em formato JSON para download."""
        flow = self.get_object()
        export_data = {
            'name': flow.name,
            'nodes': flow.nodes,
            'edges': flow.edges
        }
        
        from django.http import JsonResponse
        response = JsonResponse(export_data)
        response['Content-Disposition'] = f'attachment; filename="flow_{flow.id}_{flow.name.replace(" ", "_")}.json"'
        return response

    @action(detail=False, methods=['post'])
    def import_flow(self, request):
        """Importa um fluxo a partir de um JSON e cria um novo fluxo."""
        import json
        from core.models import ChatbotFlow, Provedor
        from core.serializers import ChatbotFlowSerializer
        
        try:
            # Pode vir como arquivo ou como JSON no body
            if 'file' in request.FILES:
                import_data = json.load(request.FILES['file'])
            else:
                import_data = request.data
            
            provedor_id = request.data.get('provedor')
            if not provedor_id:
                return Response({'error': 'ID do provedor é obrigatório'}, status=status.HTTP_400_BAD_REQUEST)
                
            provedor = Provedor.objects.get(id=provedor_id)
            
            # Criar novo fluxo herdando as configurações
            new_flow = ChatbotFlow.objects.create(
                name=f"{import_data.get('name', 'Fluxo Importado')} (Cópia)",
                nodes=import_data.get('nodes', []),
                edges=import_data.get('edges', []),
                provedor=provedor,
                is_active=True
            )
            
            serializer = ChatbotFlowSerializer(new_flow)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"[CHATBOT-FLOW] Erro ao importar fluxo: {str(e)}")
            return Response({'error': f'Erro ao importar fluxo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)


class PlanoViewSet(viewsets.ModelViewSet):
    """CRUD de Planos de Internet por provedor"""
    def get_serializer_class(self):
        from core.serializers import PlanoSerializer
        return PlanoSerializer

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from core.models import Plano
        user = self.request.user
        queryset = Plano.objects.all()

        if user.user_type != 'superadmin':
            provedores = Provedor.objects.filter(admins=user)
            queryset = queryset.filter(provedor__in=provedores)

        provedor_id = self.request.query_params.get('provedor')
        if provedor_id:
            queryset = queryset.filter(provedor_id=provedor_id)

        return queryset.order_by('ordem', 'nome')

    def perform_create(self, serializer):
        if 'provedor' not in serializer.validated_data:
            provedor = self.request.user.provedores_admin.first()
            if provedor:
                serializer.save(provedor=provedor)
            else:
                serializer.save()
        else:
            serializer.save()


class RespostaRapidaViewSet(viewsets.ModelViewSet):
    """CRUD de Respostas Rápidas por provedor"""
    def get_serializer_class(self):
        from core.serializers import RespostaRapidaSerializer
        return RespostaRapidaSerializer

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        from core.models import RespostaRapida
        user = self.request.user
        queryset = RespostaRapida.objects.all()

        if user.user_type != 'superadmin':
            provedores = Provedor.objects.filter(admins=user)
            queryset = queryset.filter(provedor__in=provedores)

        provedor_id = self.request.query_params.get('provedor')
        if provedor_id:
            queryset = queryset.filter(provedor_id=provedor_id)

        titulo = self.request.query_params.get('titulo')
        if titulo:
            queryset = queryset.filter(titulo__istartswith=titulo)

        return queryset.order_by('titulo')

    def perform_create(self, serializer):
        provedor = serializer.validated_data.get('provedor')
        if not provedor:
            provedor = self.request.user.provedores_admin.first()
        serializer.save(provedor=provedor, criado_por=self.request.user)

    def perform_update(self, serializer):
        serializer.save()


def _provider_gallery_allowed_provedor_ids(user):
    """IDs de provedor que o usuário pode administrar (None = superadmin, todos)."""
    if getattr(user, 'user_type', None) == 'superadmin':
        return None
    allowed = set()
    if getattr(user, 'provedor_id', None):
        allowed.add(user.provedor_id)
    allowed.update(Provedor.objects.filter(admins=user).values_list('id', flat=True))
    try:
        from conversations.models import TeamMember
        tm = TeamMember.objects.filter(user=user).select_related('team__provedor').first()
        if tm and tm.team and tm.team.provedor_id:
            allowed.add(tm.team.provedor_id)
    except Exception:
        pass
    return allowed


class ProviderGalleryImageViewSet(viewsets.ModelViewSet):
    """Galeria de imagens do provedor para uso no chatbot."""
    serializer_class = ProviderGalleryImageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        user = self.request.user
        # Listagem: só ativos. Detalhe/DELETE/PATCH: inclui inativos para poder
        # remover registros legados (soft-delete) e linhas com ativo=False.
        queryset = ProviderGalleryImage.objects.all()
        if getattr(self, 'action', None) == 'list':
            queryset = queryset.filter(ativo=True)
        provedor_id = self.request.query_params.get('provedor')

        # Se o frontend informar provedor explicitamente, usar esse filtro direto.
        # Isso evita falsos vazios quando o vínculo do usuário com provedor
        # não está no campo esperado (admins/provedor_id/teammember).
        if provedor_id:
            try:
                provedor_pk = int(str(provedor_id).strip())
            except (TypeError, ValueError):
                return queryset.none().order_by('nome', '-created_at')
            qs = queryset.filter(provedor_id=provedor_pk)
            allowed = _provider_gallery_allowed_provedor_ids(user)
            if allowed is None or provedor_pk in allowed:
                return qs.order_by('nome', '-created_at')
            return qs.filter(criado_por=user).order_by('nome', '-created_at')

        if user.user_type != 'superadmin':
            allowed_provedor_ids = _provider_gallery_allowed_provedor_ids(user) or set()
            queryset = queryset.filter(provedor_id__in=allowed_provedor_ids or [-1])

        return queryset.order_by('nome', '-created_at')

    def perform_create(self, serializer):
        provedor = serializer.validated_data.get('provedor')
        if not provedor:
            if getattr(self.request.user, 'provedor_id', None):
                provedor = Provedor.objects.filter(id=self.request.user.provedor_id).first()
            if not provedor:
                provedor = self.request.user.provedores_admin.first()

        if not provedor:
            raise PermissionDenied("Provedor não identificado para este usuário.")

        serializer.save(provedor=provedor, criado_por=self.request.user, ativo=True)

    def perform_destroy(self, instance):
        """Remove definitivamente o registro e o arquivo em disco."""
        try:
            if instance.imagem:
                instance.imagem.delete(save=False)
        except Exception:
            pass
        instance.delete()


@require_http_methods(["GET"])
def serve_provider_gallery_media(request, image_id):
    """Serve imagem da galeria por id (link utilizado pelo chatbot)."""
    try:
        img = ProviderGalleryImage.objects.get(id=image_id, ativo=True)
    except ProviderGalleryImage.DoesNotExist as exc:
        raise Http404("Imagem não encontrada") from exc

    if not img.imagem or not img.imagem.name:
        raise Http404("Arquivo não encontrado")

    file_path = img.imagem.path
    if not os.path.exists(file_path):
        raise Http404("Arquivo não existe")

    response = FileResponse(open(file_path, "rb"), content_type="image/*")
    response["Access-Control-Allow-Origin"] = "*"
    response["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
    return response


class UserReminderViewSet(viewsets.ModelViewSet):
    serializer_class = UserReminderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # Apenas os lembretes do próprio usuário
        return UserReminder.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def check(self, request):
        """
        Endpoint usado pelo polling do frontend para buscar lembretes que
        atingiram o horário agendado e ainda não foram notificados.
        """
        now = timezone.now()
        # Lembretes do usuário cuja hora já passou e não foram notificados
        reminders = UserReminder.objects.filter(
            user=request.user,
            scheduled_time__lte=now,
            is_notified=False
        )
        
        serializer = self.get_serializer(reminders, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'])
    def mark_notified(self, request, pk=None):
        """
        Marca um lembrete específico como notificado.
        """
        reminder = self.get_object()
        reminder.is_notified = True
        reminder.save(update_fields=['is_notified'])
        return Response({'status': 'notified'})

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

@login_required
def super_admin_contacts(request):
    """
    View para o superadmin visualizar todos os contatos de todos os provedores.
    """
    if request.user.user_type != 'superadmin':
        raise PermissionDenied("Apenas o superadmin pode acessar esta página.")
    
    contacts = Contact.objects.all().select_related('provedor')
    
    # Filtros
    provedor_id = request.GET.get('provedor_id')
    if provedor_id:
        contacts = contacts.filter(provedor_id=provedor_id)
        
    query = request.GET.get('q')
    if query:
        contacts = contacts.filter(
            Q(name__icontains=query) | 
            Q(phone__icontains=query) | 
            Q(email__icontains=query)
        )
    
    all_provedores = Provedor.objects.all().order_by('nome')
    
    context = {
        'contacts': contacts.order_by('-created_at'),
        'all_provedores': all_provedores,
        'request': request
    }
    
    return render(request, 'super_admin/all_contacts.html', context)

@login_required
def super_admin_contact_delete(request, pk):
    """
    View para o superadmin excluir um contato permanentemente.
    """
    if request.user.user_type != 'superadmin':
        raise PermissionDenied("Apenas o superadmin pode excluir contatos.")
    
    contact = get_object_or_404(Contact, pk=pk)
    
    if request.method == 'POST':
        name = contact.name
        provedor_nome = contact.provedor.nome if contact.provedor else "Nenhum"
        contact.delete()
        
        # Registrar auditoria
        AuditLog.objects.create(
            user=request.user,
            action='delete',
            details=f"Superadmin excluiu cliente {name} do provedor {provedor_nome}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        messages.success(request, f"Cliente {name} excluído com sucesso.")
        return redirect('super_admin_contacts')
    
    return redirect('super_admin_contacts')

