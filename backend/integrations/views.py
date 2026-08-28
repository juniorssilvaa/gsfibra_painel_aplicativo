from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db import models
from django.conf import settings
from core.models import CompanyUser
from .models import TelegramIntegration, EmailIntegration, WhatsAppIntegration, WebchatIntegration
from .serializers import (
    TelegramIntegrationSerializer, EmailIntegrationSerializer,
    WhatsAppIntegrationSerializer, WebchatIntegrationSerializer
)
from .telegram_service import telegram_manager
from .email_service import email_manager
import asyncio
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
import tempfile
import traceback
from conversations.models import Contact, Conversation, Message, Inbox
from core.models import Company
from django.utils import timezone
from core.openai_service import openai_service
from core.models import Provedor
from core.models import SystemConfig
from integrations.asaas_service import AsaasService
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

logger = logging.getLogger(__name__)
from django.conf import settings
from datetime import datetime, timedelta


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
        })


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
        # IMPORTANTE: No webhook da Uazapi, a mensagem está em data.message, não em data.data
        msg_data = data.get('message') or data.get('data') or {}
        
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
        # Primeiro, buscar conversa ativa (não fechada, incluindo 'closing' para verificar tolerância)
        existing_conversation = ConversationModel.objects.filter(
            contact=contact,
            inbox__channel_type='whatsapp',
            status__in=['open', 'snoozed', 'pending', 'closing']  # Incluir 'closing' para verificar tolerância
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
            elif existing_conversation.status == 'closing':
                # Conversa está em estado 'closing' - verificar se está dentro da janela de tolerância
                from conversations.closing_service import closing_service
                
                if closing_service.should_reopen(existing_conversation):
                    # Dentro da janela de tolerância - reabrir a conversa
                    logger.info(f"[UAZAPI] Reabrindo conversa {existing_conversation.id} que estava em 'closing' (dentro da janela de tolerância)")
                    existing_conversation.reopen_from_closing()
                    conversation = existing_conversation
                    if conversation.inbox != inbox:
                        conversation.inbox = inbox
                        conversation.save()
                    
                    # Resetar estado do chatbot ao reabrir (Reset de Fluxo e Cronômetro)
                    try:
                        from core.redis_memory_service import redis_memory_service
                        redis_memory_service.clear_memory_sync(
                            conversation.inbox.provedor_id if conversation.inbox else None,
                            conversation.id,
                            conversation.inbox.channel_type if conversation.inbox else 'whatsapp',
                            contact.phone
                        )
                        # Limpar metadados de nó de fluxo antigos se existirem
                        if 'chatbot_node_id' in conversation.additional_attributes:
                            del conversation.additional_attributes['chatbot_node_id']
                        if 'chatbot_flow_id' in conversation.additional_attributes:
                            del conversation.additional_attributes['chatbot_flow_id']
                        
                        # Resetar TIMESTAMP para o cronômetro do Dashboard começar do zero (como se fosse novo ciclo)
                        from django.utils import timezone
                        # Usamos .update() para contornar o auto_now_add=True
                        ConversationModel.objects.filter(id=conversation.id).update(created_at=timezone.now())
                        conversation.save(update_fields=['additional_attributes'])
                    except Exception as e:
                        logger.error(f"Erro ao resetar chatbot na reabertura da conversa {conversation.id}: {e}")
                        
                    conv_created = False
                else:
                    # Fora da janela de tolerância - criar nova conversa
                    logger.info(f"[UAZAPI] Conversa {existing_conversation.id} em 'closing' fora da janela de tolerância. Criando nova conversa.")
                    # Limpar memória Redis total (Reset de IA e Cronômetro)
                    try:
                        from core.redis_memory_service import redis_memory_service
                        redis_memory_service.clear_conversation_memory_sync(
                            provedor_id=existing_conversation.inbox.provedor_id if existing_conversation.inbox else None,
                            conversation_id=existing_conversation.id
                        )
                        redis_memory_service.clear_memory_sync(
                            existing_conversation.inbox.provedor_id if existing_conversation.inbox else None,
                            existing_conversation.id,
                            existing_conversation.inbox.channel_type if existing_conversation.inbox else 'whatsapp',
                            contact.phone
                        )
                    except Exception as e:
                        logger.error(f"Erro ao limpar memória total {existing_conversation.id}: {e}")
                    
                    # Criar nova conversa para novo atendimento (Reset de Cronômetro)
                    conversation = ConversationModel.objects.create(
                        contact=contact,
                        inbox=inbox,
                        status='snoozed',  # Nova conversa começa com IA
                        assignee=None,
                        additional_attributes={
                            'instance': instance,
                            'event': event_type,
                            'reset_cycle': True # Flag para identificar novo ciclo
                        }
                    )
                    conv_created = True
            else:
                # Conversa estava fechada ('closed') - verificar se há CSAT pendente primeiro
                
                # Verificar se há CSAT pendente para esta conversa
                from conversations.models import CSATRequest
                csat_request = CSATRequest.objects.filter(
                    conversation=existing_conversation,
                    status='sent'
                ).first()
                
                if csat_request:
                    # Processar CSAT SEM reabrir conversa - apenas usar a conversa fechada
                    # A IA deve apenas agradecer, não iniciar novo atendimento
                    conversation = existing_conversation
                    # Garantir que permaneça fechada
                    if conversation.status != 'closed':
                        conversation.status = 'closed'
                        conversation.save()
                    conv_created = False
                else:
                    # Limpar memória Redis total (Reset de IA e Cronômetro)
                    try:
                        from core.redis_memory_service import redis_memory_service
                        redis_memory_service.clear_conversation_memory_sync(
                            provedor_id=existing_conversation.inbox.provedor_id if existing_conversation.inbox else None,
                            conversation_id=existing_conversation.id
                        )
                        redis_memory_service.clear_memory_sync(
                            existing_conversation.inbox.provedor_id if existing_conversation.inbox else None,
                            existing_conversation.id,
                            existing_conversation.inbox.channel_type if existing_conversation.inbox else 'whatsapp',
                            contact.phone
                        )
                    except Exception as e:
                        logger.error(f"Erro ao limpar memória total após fechamento {existing_conversation.id}: {e}")
                    
                    # Criar nova conversa para novo atendimento (Reset de Cronômetro)
                    conversation = ConversationModel.objects.create(
                        contact=contact,
                        inbox=inbox,
                        status='snoozed',  # Nova conversa começa com IA
                        assignee=None,
                        additional_attributes={
                            'instance': instance,
                            'event': event_type,
                            'reset_cycle': True
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
            
            if csat_pendente:
                logger.info(f"CSAT pendente encontrado para conversa {conversation.id}, status={csat_pendente.status}")
        else:
            csat_pendente = None
        
        if csat_pendente and content and str(content).strip():
            logger.info(f"Processando resposta CSAT para conversa {conversation.id}: '{content[:50]}...'")
            
            # Tentar processar como feedback CSAT
            csat_feedback = CSATAutomationService.process_csat_response(
                message_text=str(content),
                conversation=conversation,
                contact=contact
            )
            
            if csat_feedback:
                # O CSAT já foi processado pelo CSATAutomationService
                # que já salvou no Supabase e enviou agradecimento
                # Apenas garantir que conversa permaneça fechada
                conversation.status = 'closed'
                conversation.save()
                
                logger.info(f"✓ CSAT processado com sucesso para conversa {conversation.id}, feedback_id={csat_feedback.id}, rating={csat_feedback.rating_value} ({csat_feedback.emoji_rating})")
                
                # Retornar ANTES de processar pela IA - não reabrir conversa
                return JsonResponse({'status': 'csat_processed', 'message': 'CSAT processado, conversa permanece fechada'})
            else:
                logger.warning(f"✗ CSAT não foi processado para conversa {conversation.id} - process_csat_response retornou None")
                
                # CÓDIGO REMOVIDO - estava causando mensagem duplicada
                """
                try:
                    # Gerar resposta personalizada com a IA
                    from core.openai_service import openai_service
                    
                    ia_result = openai_service.generate_response_sync(
                        mensagem=str(content),
                        provedor=provedor,
                        contexto={'conversation': conversation, 'canal': 'whatsapp'}
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
        # IMPORTANTE: Fazer isso ANTES de definir content como "Mensagem de voz"
        # Garantir que instance está definido antes de usar na transcrição
        if not instance:
            instance = data.get('instance') or data.get('owner') or data.get('instanceName')
        
        try:
            if db_message_type in ['audio', 'ptt']:
                logger.info(f"[UAZAPI] Detectada mensagem de áudio (tipo: {db_message_type}) para conversa {conversation.id if conversation else 'N/A'}")
                
                # Tentar extrair o ID da mensagem de áudio de várias formas
                # IMPORTANTE: Verificar valores vazios também
                audio_msg_id = None
                
                # Log detalhado para debug
                logger.info(f"[UAZAPI] Tentando extrair message_id. msg_data type: {type(msg_data)}, keys: {list(msg_data.keys()) if isinstance(msg_data, dict) else 'N/A'}")
                if isinstance(msg_data, dict):
                    logger.info(f"[UAZAPI] msg_data['id'] = {msg_data.get('id')}, msg_data['messageid'] = {msg_data.get('messageid')}")
                
                # Tentar msg_data primeiro (formato mais comum)
                if isinstance(msg_data, dict):
                    # Tentar 'id' primeiro (formato completo: "559491493481:3F69361F332A29821201")
                    temp_id = msg_data.get('id')
                    if temp_id and str(temp_id).strip():
                        audio_msg_id = str(temp_id).strip()
                        logger.info(f"[UAZAPI] ✓ message_id extraído de msg_data['id']: {audio_msg_id}")
                    
                    # Se não encontrou, tentar 'messageid' (formato curto: "3F69361F332A29821201")
                    if not audio_msg_id:
                        temp_id = msg_data.get('messageid')
                        if temp_id and str(temp_id).strip():
                            audio_msg_id = str(temp_id).strip()
                            logger.info(f"[UAZAPI] ✓ message_id extraído de msg_data['messageid']: {audio_msg_id}")
                    
                    # Tentar 'messageId' (camelCase)
                    if not audio_msg_id:
                        temp_id = msg_data.get('messageId')
                        if temp_id and str(temp_id).strip():
                            audio_msg_id = str(temp_id).strip()
                            logger.info(f"[UAZAPI] ✓ message_id extraído de msg_data['messageId']: {audio_msg_id}")
                
                # Se ainda não encontrou, tentar em data.message (estrutura do webhook Uazapi)
                if not audio_msg_id and isinstance(data, dict):
                    # Tentar data.get('message', {}).get('id')
                    message_obj = data.get('message', {})
                    if isinstance(message_obj, dict):
                        temp_id = message_obj.get('id')
                        if temp_id and str(temp_id).strip():
                            audio_msg_id = str(temp_id).strip()
                            logger.info(f"[UAZAPI] ✓ message_id extraído de data['message']['id']: {audio_msg_id}")
                        
                        # Tentar message_obj.get('messageid')
                        if not audio_msg_id:
                            temp_id = message_obj.get('messageid')
                            if temp_id and str(temp_id).strip():
                                audio_msg_id = str(temp_id).strip()
                                logger.info(f"[UAZAPI] ✓ message_id extraído de data['message']['messageid']: {audio_msg_id}")
                
                if audio_msg_id:
                    logger.info(f"[UAZAPI] Iniciando transcrição de áudio para conversa {conversation.id}, message_id={audio_msg_id}")
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
                            # Validar se a chave não está vazia e tem tamanho mínimo (chaves OpenAI geralmente têm pelo menos 20 caracteres)
                            if openai_key and len(openai_key) >= 20:
                                logger.info(f"[UAZAPI] ✓ Chave OpenAI para transcrição configurada (tamanho: {len(openai_key)} caracteres)")
                            elif openai_key:
                                logger.error(f"[UAZAPI] ✗ Chave OpenAI muito curta ou inválida (tamanho: {len(openai_key)} caracteres). Configure uma chave válida no painel do superadmin.")
                                openai_key = None
                            else:
                                logger.warning(f"[UAZAPI] ✗ Campo openai_transcription_api_key está vazio no SystemConfig")
                        else:
                            logger.warning(f"[UAZAPI] ✗ Campo openai_transcription_api_key não configurado no SystemConfig")
                    else:
                        logger.warning(f"[UAZAPI] ✗ SystemConfig não encontrado")
                    
                    if not openai_key:
                        logger.warning(f"[UAZAPI] ✗ Chave de API OpenAI não disponível, não será possível transcrever o áudio. Configure openai_transcription_api_key no painel do superadmin.")
                    else:
                        # PRIMEIRA TRANSCRIÇÃO
                        # IMPORTANTE: A Uazapi geralmente precisa apenas do messageid (sem o prefixo do owner)
                        transcription_message_id = audio_msg_id
                        if ':' in str(audio_msg_id):
                            # Se o formato for "559491493481:3FA279469399EECFE274", usar apenas a parte após ":"
                            transcription_message_id = str(audio_msg_id).split(':', 1)[1]
                            logger.info(f"[UAZAPI] message_id formatado para transcrição: {audio_msg_id} -> {transcription_message_id}")
                        
                        logger.info(f"[UAZAPI] Fazendo primeira transcrição do áudio {transcription_message_id} (instance: {instance})...")
                        # Log detalhado sem expor a chave completa
                        openai_key_preview = f"{openai_key[:10]}...{openai_key[-4:]}" if openai_key and len(openai_key) > 14 else "NÃO configurada"
                        logger.info(f"[UAZAPI] Parâmetros: id={transcription_message_id}, transcribe=True, openai_apikey={openai_key_preview} (tamanho: {len(openai_key) if openai_key else 0}), instance={instance}")
                        
                        # Validar chave antes de enviar
                        if not openai_key or len(openai_key.strip()) < 20:
                            logger.error(f"[UAZAPI] ✗ Chave OpenAI inválida ou muito curta. Não será possível transcrever.")
                            dl1 = {"error": "Chave OpenAI inválida", "raw": "Chave não configurada ou muito curta"}
                        else:
                            dl1 = client.download_message(
                                message_id=transcription_message_id,
                                instance_id=instance,
                                generate_mp3=True,
                                return_base64=False,
                                return_link=True,
                                transcribe=True,
                                openai_apikey=openai_key.strip()
                            )
                        logger.info(f"[UAZAPI] Resposta da transcrição: {str(dl1)[:200]}...")
                        
                        if isinstance(dl1, dict) and 'error' in dl1:
                            error_msg = dl1.get('error', '')
                            error_raw = dl1.get('raw', '')[:500] if dl1.get('raw') else ''
                            logger.error(f"[UAZAPI] Erro na primeira transcrição: {error_msg}")
                            if error_raw:
                                logger.error(f"[UAZAPI] Detalhes do erro: {error_raw}")
                        
                        transcription1 = dl1.get('transcription') if isinstance(dl1, dict) and 'transcription' in dl1 else None
                        if transcription1:
                            logger.info(f"[UAZAPI] ✓ Primeira transcrição obtida: {transcription1[:100]}...")
                        else:
                            logger.warning(f"[UAZAPI] Primeira transcrição não retornada. Resposta: {dl1}")
                        
                        # Delay dinâmico entre transcrições
                        if enable_double and transcription1:
                            import time
                            time.sleep(delay_between)
                            
                            # SEGUNDA TRANSCRIÇÃO (para garantir precisão)
                            logger.info(f"[UAZAPI] Fazendo segunda transcrição do áudio {transcription_message_id}...")
                            # Validar chave antes de enviar
                            if not openai_key or len(openai_key.strip()) < 20:
                                logger.error(f"[UAZAPI] ✗ Chave OpenAI inválida ou muito curta. Não será possível fazer segunda transcrição.")
                                dl2 = {"error": "Chave OpenAI inválida", "raw": "Chave não configurada ou muito curta"}
                            else:
                                dl2 = client.download_message(
                                    message_id=transcription_message_id,
                                    instance_id=instance,
                                    generate_mp3=True,
                                    return_base64=False,
                                    return_link=True,
                                    transcribe=True,
                                    openai_apikey=openai_key.strip()
                                )
                            
                            if isinstance(dl2, dict) and 'error' in dl2:
                                logger.error(f"[UAZAPI] Erro na segunda transcrição: {dl2.get('error')} - {dl2.get('raw', '')[:200]}")
                            
                            transcription2 = dl2.get('transcription') if isinstance(dl2, dict) and 'transcription' in dl2 else None
                            if transcription2:
                                logger.info(f"[UAZAPI] ✓ Segunda transcrição obtida: {transcription2[:100]}...")
                            else:
                                logger.warning(f"[UAZAPI] Segunda transcrição não retornada. Resposta: {dl2}")
                            
                            # COMPARAR TRANSCRIÇÕES E ESCOLHER A MELHOR
                            final_transcription = None
                            if transcription1 and transcription2:
                                # Se as transcrições são idênticas, usar qualquer uma
                                if transcription1.strip().lower() == transcription2.strip().lower():
                                    final_transcription = transcription1
                                    logger.info(f"[UAZAPI] Transcrições idênticas, usando primeira")
                                else:
                                    # Se diferentes, usar a mais longa (geralmente mais precisa)
                                    if len(transcription1) > len(transcription2):
                                        final_transcription = transcription1
                                        logger.info(f"[UAZAPI] Transcrições diferentes, usando primeira (mais longa)")
                                    else:
                                        final_transcription = transcription2
                                        logger.info(f"[UAZAPI] Transcrições diferentes, usando segunda (mais longa)")
                            elif transcription1:
                                final_transcription = transcription1
                                logger.info(f"[UAZAPI] Usando apenas primeira transcrição (segunda falhou)")
                            elif transcription2:
                                final_transcription = transcription2
                                logger.info(f"[UAZAPI] Usando apenas segunda transcrição (primeira falhou)")
                            else:
                                logger.warning(f"[UAZAPI] Nenhuma transcrição foi retornada (primeira e segunda falharam)")
                        else:
                            # TRANSCRIÇÃO ÚNICA (quando dupla está desabilitada ou primeira falhou)
                            final_transcription = transcription1
                            if final_transcription:
                                logger.info(f"[UAZAPI] Transcrição única concluída")
                            else:
                                logger.warning(f"[UAZAPI] Transcrição única falhou")
                        
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
                            logger.info(f"[UAZAPI] ✓ Transcrição concluída e definida como conteúdo: {final_transcription[:100]}...")
                        else:
                            logger.warning(f"[UAZAPI] ✗ Transcrição falhou, mantendo 'Mensagem de voz' como conteúdo")
                else:
                    logger.warning(f"[UAZAPI] Não foi possível extrair message_id do áudio. msg_data keys: {list(msg_data.keys()) if isinstance(msg_data, dict) else 'N/A'}")
        except Exception as e:
            logger.error(f"[UAZAPI] Erro ao processar transcrição de áudio para conversa {conversation.id}: {str(e)}", exc_info=True)

        # 2. Acionar IA para resposta automática (apenas se não foi CSAT e não estiver atribuída)
        
        # Log do conteúdo antes de chamar IA (para debug)
        logger.info(f"[UAZAPI] Conteúdo antes de chamar IA: '{content}' (tipo: {type(content)}, tamanho: {len(str(content)) if content else 0})")
        
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
            else:
                # Verificar se há CSAT pendente - se houver, NÃO chamar IA (já foi processado acima)
                csat_pendente_verificar = None
                if CSATRequest:
                    csat_pendente_verificar = CSATRequest.objects.filter(
                        conversation=conversation,
                        status='sent'
                    ).first()
                
                # Verificar se conversa está atribuída ou em espera
                # Permitir resposta da IA se não estiver atribuída, não estiver fechada E não houver CSAT pendente
                if (conversation.assignee is None and 
                      conversation.status not in ['closed', 'resolved'] and
                      not csat_pendente_verificar):
                    try:
                        # ==========================================================
                        # CHATBOT ENGINE / ROUTING LOGIC (UAZAPI)
                        # ==========================================================
                        bot_mode = getattr(provedor, 'bot_mode', 'ia')
                        chatbot_handled = False
                        
                        if bot_mode == 'chatbot':
                            logger.info(f"[UAZAPI] Provador {provedor.id} em modo CHATBOT. Invocando ChatbotEngine.")
                            try:
                                from asgiref.sync import async_to_sync
                                from core.chatbot_engine import ChatbotEngine
                                
                                async def run_chatbot_engine():
                                    canal = conversation.inbox.get_canal_instance()
                                    canal_id = canal.id if canal else None
                                    return await ChatbotEngine.process_message(
                                        provedor_id=provedor.id,
                                        conversation_id=conversation.id,
                                        message_content=str(content) if content else "",
                                        button_id=None, # Poderia extrair button_id se disponível no Uazapi
                                        canal_id=canal_id
                                    )
                                
                                chatbot_handled = async_to_sync(run_chatbot_engine)()
                                if chatbot_handled:
                                    logger.info(f"[UAZAPI] Mensagem processada pelo Chatbot Engine na conversa {conversation.id}")
                                    ia_result = {'success': True, 'chatbot_handled': True}
                                    # Pular IA se o chatbot tratou
                                    continue_to_ia = False
                                else:
                                    logger.warning(f"[UAZAPI] Provedor em modo CHATBOT mas nenhum nó foi executado.")
                                    continue_to_ia = False # Mesmo que não trate, modo Chatbot bloqueia IA
                            except Exception as chatbot_err:
                                logger.error(f"[UAZAPI] Erro ao invocar Chatbot Engine: {chatbot_err}", exc_info=True)
                                continue_to_ia = False
                        else:
                            continue_to_ia = True

                        if continue_to_ia:
                            logger.info(f"[UAZAPI] Chamando IA (Gemini) para gerar resposta. Conteúdo: {str(content)[:100]}...")
                            ia_result = openai_service.generate_response_sync(
                                mensagem=str(content),  # Garantir que é string
                                provedor=provedor,
                                contexto={'conversation': conversation, 'canal': 'whatsapp'}
                            )
                        
                        logger.info(f"[UAZAPI] Resposta da IA obtida: success={ia_result.get('success')}")
                        
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
                        logger.error(f"[UAZAPI] Erro ao chamar IA: {str(e)}", exc_info=True)
                        ia_result = {'success': False, 'erro': str(e)}
                else:
                    motivo = []
                    if conversation.assignee:
                        motivo.append(f"atribuída a {conversation.assignee}")
                    if conversation.status in ['closed', 'resolved']:
                        motivo.append(f"status {conversation.status}")
                    if csat_pendente_verificar:
                        motivo.append("CSAT pendente")
                    motivo_str = ", ".join(motivo) if motivo else "desconhecido"
                    logger.info(f"[UAZAPI] IA não chamada - conversa {motivo_str}")
                    ia_result = {'success': False, 'motivo': f'Conversa {motivo_str}'}
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
                    
                    # Se o erro for de chave não configurada, enviar mensagem de erro ao cliente
                    if 'Chave da API Google não configurada' in str(erro_ia) or 'chave da API' in str(erro_ia).lower():
                        resposta_ia = "Desculpe, estou com dificuldades técnicas no momento. Por favor, tente novamente em alguns instantes ou entre em contato com nosso suporte."
                        logger.error(f"[UAZAPI] Chave da API Google não configurada - enviando mensagem de erro genérica ao cliente")
                    # Se o erro for de pacote não instalado (google-genai)
                    elif 'google-genai' in str(erro_ia).lower() or 'nova API do Google' in str(erro_ia):
                        logger.error(f"[UAZAPI] Pacote google-genai não instalado - {erro_ia}")
                        resposta_ia = "Desculpe, estou com dificuldades técnicas no momento. Por favor, tente novamente em alguns instantes ou entre em contato com nosso suporte."
                else:
                    logger.warning(f"[UAZAPI] ia_result não definido para conversa {conversation.id}")
        
        # 🚨 SEGURANÇA CRÍTICA: Remover qualquer código antes de enviar ao cliente
        if resposta_ia:
            from core.ai_response_formatter import AIResponseFormatter
            formatter = AIResponseFormatter()
            resposta_ia = formatter.remover_exposicao_funcoes(resposta_ia)
        
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
                    
                    # 🚨 REGRA DE OURO: Detectar formato de contrato e separar mensagens com delay
                    # Detectar formato novo: "Contrato:\n\n[NOME]\n\n1 - Contrato..."
                    import re
                    formato_contrato_detectado = False
                    dados_contrato = None
                    pergunta_ajuda = None
                    
                    # Padrão 1: Formato novo "Contrato:\n\n[NOME]\n\n1 - Contrato..."
                    if re.search(r'Contrato:\s*\n\s*\n\s*[A-Z\s]+\s*\n\s*\n\s*\d+\s*-\s*Contrato', resposta_ia, re.IGNORECASE | re.MULTILINE):
                        formato_contrato_detectado = True
                        # Extrair nome do cliente para usar na pergunta
                        nome_match = re.search(r'Contrato:\s*\n\s*\n\s*([A-Z\s]+?)\s*\n\s*\n', resposta_ia, re.IGNORECASE | re.MULTILINE)
                        primeiro_nome = None
                        if nome_match:
                            nome_completo = nome_match.group(1).strip()
                            # Extrair primeiro nome (primeira palavra)
                            primeiro_nome = nome_completo.split()[0] if nome_completo.split() else None
                            # Capitalizar primeira letra
                            if primeiro_nome:
                                primeiro_nome = primeiro_nome.capitalize()
                        
                        # Separar dados do contrato (tudo até encontrar pergunta ou fim)
                        # Procurar por perguntas comuns após os dados
                        perguntas_pattern = r'(Como posso|Em que posso|Como posso te ajudar|Em que posso te ajudar|Posso ajudar)'
                        match_pergunta = re.search(perguntas_pattern, resposta_ia, re.IGNORECASE)
                        
                        if match_pergunta:
                            # Separar em duas partes
                            dados_contrato = resposta_ia[:match_pergunta.start()].strip()
                            pergunta_original = resposta_ia[match_pergunta.start():].strip()
                            # Se não tem primeiro nome na pergunta, adicionar
                            if primeiro_nome and primeiro_nome.lower() not in pergunta_original.lower():
                                pergunta_ajuda = f"Como posso te ajudar hoje, {primeiro_nome}?"
                            else:
                                pergunta_ajuda = pergunta_original
                        else:
                            # Se não tem pergunta, usar apenas os dados e criar pergunta
                            dados_contrato = resposta_ia.strip()
                            if primeiro_nome:
                                pergunta_ajuda = f"Como posso te ajudar hoje, {primeiro_nome}?"
                            else:
                                pergunta_ajuda = "Como posso te ajudar hoje?"
                    
                    # Padrão 2: Formato antigo "CONFIRMAÇÃO DE DADOS DO CONTRATO"
                    elif 'CONFIRMAÇÃO DE DADOS DO CONTRATO' in resposta_ia and 'Essas informações estão corretas?' in resposta_ia:
                        formato_contrato_detectado = True
                        partes = resposta_ia.split('Essas informações estão corretas?')
                        dados_contrato = partes[0].strip()
                        pergunta_ajuda = 'Essas informações estão corretas?'
                    
                    if formato_contrato_detectado and dados_contrato:
                        # PASSO 1: VALIDAR QUEBRAS DE LINHA
                        dados_contrato = validar_quebras_linha(dados_contrato)
                        
                        # PASSO 2: Enviar dados do contrato com delay
                        payload_dados = {
                            'number': clean_number,
                            'delay': 1000,
                            'text': dados_contrato
                        }
                        send_resp_dados = requests.post(
                            f"{uazapi_url.rstrip('/')}/send/text",
                            headers={'token': uazapi_token, 'Content-Type': 'application/json'},
                            json=payload_dados,
                            timeout=10
                        )
                        
                        if send_resp_dados.status_code == 200:
                            # Aguardar 2-3 segundos antes de enviar a pergunta (delay entre mensagens)
                            import time
                            time.sleep(2.5)  # Delay de 2.5 segundos
                            
                            # PASSO 3: Enviar pergunta com delay
                            if pergunta_ajuda:
                                payload_pergunta = {
                                    'number': clean_number,
                                    'delay': 1000,
                                    'text': pergunta_ajuda
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
                        # Mensagem normal - verificar se é primeira mensagem dividida
                        # 🚨 REGRA DE OURO: Primeira mensagem deve ser dividida em partes com delay
                        if " | " in resposta_ia:
                            # É primeira mensagem dividida - enviar em partes com delay
                            partes = [parte.strip() for parte in resposta_ia.split(" | ") if parte.strip()]
                            
                            if partes:
                                import time
                                success = False
                                
                                # Enviar cada parte com delay entre elas
                                for i, parte in enumerate(partes):
                                    # PASSO 1: VALIDAR QUEBRAS DE LINHA
                                    parte_formatada = validar_quebras_linha(parte)
                                    
                                    # PASSO 2: Enviar parte com delay
                                    payload = {
                                        'number': clean_number,
                                        'delay': 1000,
                                        'text': parte_formatada
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
                                        
                                        # Aguardar delay entre mensagens (exceto na última)
                                        if i < len(partes) - 1:
                                            time.sleep(1.5)  # Delay de 1.5 segundos entre partes
                                    else:
                                        logger.warning(f"[UAZAPI] Erro ao enviar parte {i+1} da primeira mensagem: {send_resp.status_code}")
                                        break
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


@csrf_exempt
def asaas_webhook(request):
    """
    Webhook do Asaas para atualizar bloqueio/desbloqueio de provedores.
    Regras:
    - Bloqueia quando houver fatura OVERDUE com mais de 3 dias.
    - Libera automaticamente quando nao houver mais faturas elegiveis para bloqueio.
    """
    # Alguns validadores de webhook testam a URL com GET/HEAD antes de salvar.
    # Retornamos 200 para validar disponibilidade do endpoint.
    if request.method in ('GET', 'HEAD'):
        return JsonResponse({'status': 'ok', 'message': 'Asaas webhook endpoint online'}, status=200)

    if request.method != 'POST':
        return JsonResponse({'error': 'Metodo nao permitido'}, status=405)

    # Validacao do token de autenticacao do webhook (configurado no painel do Asaas)
    config = SystemConfig.objects.filter(key='system_config').first() or SystemConfig.objects.first()
    expected_token = (getattr(config, 'asaas_webhook_auth_token', None) or '').strip()

    if not expected_token:
        logger.error("[AsaasWebhook] Token de autenticacao do webhook nao configurado no SystemConfig.")
        return JsonResponse({'error': 'Webhook auth token nao configurado no sistema'}, status=503)

    received_token = (
        request.headers.get('asaas-access-token')
        or request.headers.get('access_token')
        or request.headers.get('token')
        or request.headers.get('Authorization')
        or request.META.get('HTTP_ASAAS_ACCESS_TOKEN')
        or request.META.get('HTTP_ACCESS_TOKEN')
        or request.META.get('HTTP_TOKEN')
        or request.META.get('HTTP_AUTHORIZATION')
        or ''
    ).strip()

    if received_token.lower().startswith('bearer '):
        received_token = received_token[7:].strip()

    import secrets
    if not received_token or not secrets.compare_digest(received_token, expected_token):
        logger.warning("[AsaasWebhook] Requisicao rejeitada por token invalido/ausente.")
        return JsonResponse({'error': 'Nao autorizado'}, status=403)

    try:
        payload = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    event = str(payload.get('event') or '').upper()
    payment = payload.get('payment') or {}
    customer_id = payment.get('customer')
    subscription_id = payment.get('subscription')

    if not customer_id and not subscription_id:
        return JsonResponse({'status': 'ignored', 'reason': 'missing_customer_or_subscription'}, status=200)

    provedor = None
    if subscription_id:
        provedor = Provedor.objects.filter(asaas_subscription_id=subscription_id).first()
    if not provedor and customer_id:
        provedor = Provedor.objects.filter(asaas_customer_id=customer_id).first()

    if not provedor:
        return JsonResponse({'status': 'ignored', 'reason': 'provider_not_found'}, status=200)

    asaas = AsaasService()
    if not asaas.access_token:
        return JsonResponse({'error': 'Asaas token nao configurado'}, status=500)

    if not provedor.asaas_subscription_id:
        return JsonResponse({'status': 'ignored', 'reason': 'provider_without_subscription'}, status=200)

    overdue_res = asaas.list_payments(subscription_id=provedor.asaas_subscription_id, status='OVERDUE')
    if not overdue_res.get('success'):
        return JsonResponse({'error': 'failed_to_sync_overdue', 'details': overdue_res.get('error')}, status=502)

    overdue_payments = overdue_res.get('data', [])
    today = timezone.now().date()
    blocking_overdues = []
    for p in overdue_payments:
        due_date_raw = p.get('dueDate')
        if not due_date_raw:
            continue
        try:
            due_date = datetime.strptime(str(due_date_raw)[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        if (today - due_date).days > 3:
            blocking_overdues.append(p)

    changed = False
    if blocking_overdues:
        block_reason = 'Bloqueado por inadimplencia Asaas (fatura vencida ha mais de 3 dias).'
        if provedor.is_active or provedor.block_reason != block_reason:
            provedor.is_active = False
            provedor.block_reason = block_reason
            changed = True
    else:
        if (not provedor.is_active) and provedor.block_reason and 'Asaas' in provedor.block_reason:
            provedor.is_active = True
            provedor.block_reason = None
            changed = True

    payment_status = (payment.get('status') or '').upper()
    if payment_status and provedor.subscription_status != payment_status:
        provedor.subscription_status = payment_status
        changed = True

    if changed:
        provedor.save(update_fields=['is_active', 'block_reason', 'subscription_status', 'updated_at'])

    return JsonResponse({
        'status': 'ok',
        'event': event,
        'provider_id': provedor.id,
        'provider_active': provedor.is_active,
        'blocking_overdues': len(blocking_overdues),
        'payment_status': payment_status
    }, status=200)

