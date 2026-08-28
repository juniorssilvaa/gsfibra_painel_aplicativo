"""
Webhooks para WhatsApp Cloud API Coexistence

Este módulo processa webhooks recebidos da Meta para o WhatsApp Cloud API.
Suporta:
- Verificação do webhook (GET) - Meta valida o endpoint
- Recebimento de eventos (POST) - Mensagens, echoes, histórico, state sync
- Validação de assinatura (X-Hub-Signature-256) para segurança

Estrutura modular:
- Handlers específicos para cada tipo de evento
- Roteamento por field name
- Processamento assíncrono e seguro
"""
import json
import logging
import hmac
import hashlib
import os
import mimetypes
from typing import Optional
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from datetime import datetime
import requests

from conversations.models import Message, Conversation, Contact
from conversations.services import ConversationNotificationService
from core.models import Provedor, Canal
from core.chatbot_engine import ChatbotEngine
from core.redis_memory_service import redis_memory_service
from integrations.models import WhatsAppIntegration

# Importar handlers modulares
from .webhook_handlers.business_status import process_business_status_update
from .webhook_handlers.account_alerts import process_account_alerts
from .webhook_handlers.templates import (
    process_template_components_update,
    process_template_quality_update,
    process_template_status_update,
    process_template_category_update,
    process_template_correct_category_detection
)
from .webhook_handlers.user_preferences import process_user_preferences
from .webhook_handlers.message_statuses import process_message_statuses

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def download_whatsapp_media(media_id: str, canal: Canal, conversation_id: int, filename_hint: str = None):
    """
    Baixa mídia da WhatsApp Cloud API e salva em MEDIA_ROOT/messages/{conversation_id}/.
    Retorna (local_url, meta) ou (None, None) em caso de falha.
    """
    if not media_id or not canal or not canal.token:
        return None, None

    phone_number_id = canal.phone_number_id
    token = canal.token

    try:
        # 1) Obter URL de download e metadados
        meta_url = f"https://graph.facebook.com/v24.0/{media_id}"
        params = {}
        if phone_number_id:
            params["phone_number_id"] = phone_number_id

        headers = {"Authorization": f"Bearer {token}"}
        meta_resp = requests.get(meta_url, headers=headers, params=params, timeout=15)
        if meta_resp.status_code != 200:
            logger.debug(f"[WhatsAppMedia] Falha meta {meta_resp.status_code}: {meta_resp.text}")
            return None, None

        meta_data = meta_resp.json()
        download_url = meta_data.get("url")
        mime_type = meta_data.get("mime_type")
        file_size = meta_data.get("file_size")
        sha256_hash = meta_data.get("sha256")

        if not download_url:
            return None, None

        # 2) Baixar binário
        file_resp = requests.get(download_url, headers=headers, timeout=30)
        if file_resp.status_code != 200:
            logger.debug(f"[WhatsAppMedia] Falha download {file_resp.status_code}: {file_resp.text[:200]}")
            return None, None

        # 3) Determinar extensão
        ext = None
        if mime_type:
            ext = mimetypes.guess_extension(mime_type)
        if not ext:
            ct = file_resp.headers.get("Content-Type")
            if ct:
                ext = mimetypes.guess_extension(ct)
        if not ext:
            if mime_type:
                if 'image' in mime_type: ext = ".jpg"
                elif 'video' in mime_type: ext = ".mp4"
                elif 'audio' in mime_type: ext = ".ogg"
            
        if not ext:
            ext = ".bin"

        import os
        import time
        
        # Lista de nomes genéricos que a Meta ou o sistema passa e que devem ser ignorados
        generic_hints = ["image", "video", "audio", "voice", "document", "image.jpg", "video.mp4", "audio.ogg"]
        
        # IMPORTANTE: Usar timestamp + ID da mídia para garantir unicidade absoluta
        ts = int(time.time())
        
        if not filename_hint or filename_hint.lower() in generic_hints:
            filename_base = f"media_{ts}_{media_id}"
        else:
            # Parece ser um nome de arquivo real (ex: documento)
            # Adicionamos o ID curto no final para evitar colisão se dois arquivos tiverem o mesmo nome
            name_without_ext, old_ext = os.path.splitext(filename_hint)
            filename_base = f"{name_without_ext}_{media_id[-6:]}"

        # Verificar se filename_base parece ser um documento (por ter extensão de documento)
        document_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
        name_without_ext, old_ext = os.path.splitext(filename_base)
        is_document_with_ext = old_ext and old_ext.lower() in document_extensions
        
        if is_document_with_ext:
            # Para documentos com extensão conhecida, preservar o filename original
            # Isso mantém o nome do arquivo como enviado pela Meta (ex: "invoice.pdf")
            filename = filename_base
        else:
            # Para outros tipos (áudio, etc), remover extensão do filename_base se existir
            # Isso evita duplicação de extensões (ex: "audio.ogg.oga")
            if old_ext:
                filename_base = name_without_ext
            
            # Adicionar a extensão correta baseada no mime_type
            if not filename_base.lower().endswith(ext):
                filename = f"{filename_base}{ext}"
            else:
                filename = filename_base

        # 4) Salvar em disco
        media_dir = os.path.join(settings.MEDIA_ROOT, "messages", str(conversation_id))
        os.makedirs(media_dir, exist_ok=True)
        file_path = os.path.join(media_dir, filename)
        with open(file_path, "wb") as f:
            f.write(file_resp.content)

        # No Windows, garantir que barras normais sejam usadas para a URL do banco
        local_url = f"/api/media/messages/{conversation_id}/{filename}/"
        local_url = local_url.replace('\\', '/')

        meta_saved = {
            "mime_type": mime_type,
            "file_size": file_size,
            "sha256": sha256_hash,
            "whatsapp_download_url": download_url,
        }
        return local_url, meta_saved
    except Exception as e:
        logger.debug(f"[WhatsAppMedia] Erro ao baixar mídia {media_id}: {e}")
        return None, None


def fetch_and_update_phone_numbers(waba_id: str, canal: Canal) -> bool:
    """Busca números do WhatsApp usando WABA ID + Access Token e atualiza o canal."""
    try:
        if not canal.token:
            return False
        
        from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
        import requests
        
        url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{waba_id}/phone_numbers"
        
        response = requests.get(
            url,
            params={"access_token": canal.token},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            phones_list = data.get("data", [])
            
            if phones_list:
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
                    
                    if is_test:
                        test_phones.append(phone)
                    else:
                        real_phones.append(phone)
                
                if real_phones:
                    phone_data = real_phones[0]
                elif test_phones:
                    phone_data = test_phones[0]
                else:
                    phone_data = phones_list[0]
                
                phone_number_id = phone_data.get("id")
                display_number = phone_data.get("display_phone_number", "")
                verified_name = phone_data.get("verified_name", "")
                code_verification_status = phone_data.get("code_verification_status", "")
                
                if not canal.phone_number_id or canal.phone_number_id != phone_number_id:
                    canal.phone_number_id = phone_number_id
                    canal.phone_number = display_number
                    canal.status = "connected"
                    
                    if not canal.dados_extras:
                        canal.dados_extras = {}
                    
                    canal.dados_extras.update({
                        "display_phone_number": display_number,
                        "verified_name": verified_name,
                        "code_verification_status": code_verification_status,
                        "last_phone_update": timezone.now().isoformat()
                    })
                    
                    canal.save()
                    return True
                return True
            else:
                return False
        else:
            return False
    
    except Exception as e:
        return False


def normalize_phone_number(phone: str) -> str:
    """
    Normaliza número de telefone para formato padrão.
    Lida com o nono dígito brasileiro para evitar duplicidade.
    """
    if not phone:
        return ""
    
    # Remover caracteres não numéricos
    import re
    cleaned = re.sub(r'\D', '', phone)
    
    # Se começar com +, o regex acima já removeu
    
    # Lógica para números brasileiros (DDI 55)
    if cleaned.startswith('55') and len(cleaned) >= 10:
        # Extrair DDD e número
        ddd_e_numero = cleaned[2:]
        
        # Se tem 10 dígitos (DDD + 8), adicionar o 9 (nono dígito)
        # Regra: DDDs 11 a 99 (todos hoje têm nono dígito no celular)
        if len(ddd_e_numero) == 10:
            # DDD (2) + Número (8) -> Adicionar 9 após o DDD
            cleaned = '55' + ddd_e_numero[:2] + '9' + ddd_e_numero[2:]
        
        # Opcional: Se quiser remover o 9 invés de adicionar, faria o contrário.
        # Mas o padrão Meta/WhatsApp Cloud API é enviar COM o 9.
            
    return cleaned


def verify_webhook_signature(request_body: bytes, signature: str) -> bool:
    """Verifica a assinatura do webhook usando X-Hub-Signature-256."""
    if not signature:
        return False
    
    if not signature.startswith("sha256="):
        return False
    
    received_hash = signature.replace("sha256=", "")
    
    app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', None)
    if not app_secret:
        return False
    
    expected_hash = hmac.new(
        app_secret.encode('utf-8'),
        request_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(received_hash, expected_hash)


def route_webhook_event(field: str, waba_id: str, value: dict):
    """
    Roteia eventos do webhook para handlers específicos.
    
    Padrão de roteamento:
    - business_status_update → CRÍTICO (atualiza status do canal)
    - account_alerts → IMPORTANTE (notifica admins)
    - message_template_components_update → OPCIONAL (atualiza templates)
    - automatic_events → IGNORAR (apenas ACK 200)
    - history → IGNORAR (apenas ACK 200)
    - Outros campos existentes → processar normalmente
    """
    # 1. business_status_update - CRÍTICO
    if field == "business_status_update":
        process_business_status_update(waba_id, value)
        return
    
    # 2. account_alerts - IMPORTANTE
    if field == "account_alerts":
        process_account_alerts(waba_id, value)
        return
    
    # 3. Templates - OPCIONAL (vários eventos)
    if field == "message_template_components_update":
        process_template_components_update(waba_id, value)
        return
    
    if field == "message_template_quality_update":
        process_template_quality_update(waba_id, value)
        return
    
    if field == "message_template_status_update":
        process_template_status_update(waba_id, value)
        return
    
    if field == "template_category_update":
        process_template_category_update(waba_id, value)
        return
    
    if field == "template_correct_category_detection":
        process_template_correct_category_detection(waba_id, value)
        return
    
    # 4. User Preferences - IMPORTANTE
    if field == "user_preferences":
        process_user_preferences(waba_id, value)
        return
    
    # 5. Message Statuses - IMPORTANTE (status de mensagens enviadas: sent, delivered, read, failed)
    if field == "statuses":
        process_message_statuses(waba_id, value)
        return
    
    # 6. automatic_events - Processar apenas typing indicators
    if field == "automatic_events":
        from .webhook_handlers.typing_indicators import process_typing_indicators
        process_typing_indicators(waba_id, value)
        return
    
    # 7. history - IGNORAR COMPLETAMENTE (pode conter payloads grandes)
    if field == "history":
        return
    
    # 8. Outros campos existentes (manter compatibilidade)
    if field == "smb_message_echoes":
        process_message_echoes(waba_id, value)
    elif field == "smb_app_state_sync":
        process_state_sync(waba_id, value)
    elif field == "messages":
        # Verificar se há statuses dentro do value (confirmações de leitura/entrega)
        if value.get("statuses"):
            process_message_statuses(waba_id, value)
        else:
            process_incoming_messages(waba_id, value)
    elif field == "phone_number_name_update" or field == "phone_number_quality_update":
        process_phone_number_update(waba_id, value)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_cloud_webhook(request):
    """
    Webhook principal para WhatsApp Cloud API
    
    Suporta:
    - GET: Verificação do webhook (challenge)
    - POST: Recebimento de eventos
    """
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        
        if mode != "subscribe":
            return JsonResponse({"error": "Invalid mode"}, status=403)
        
        if not challenge:
            return JsonResponse({"error": "Challenge required"}, status=400)
        
        expected_token = getattr(settings, 'WHATSAPP_WEBHOOK_VERIFY_TOKEN', None)
        if not expected_token:
            return JsonResponse({"error": "Verification token not configured"}, status=500)
        
        if not token or token != expected_token:
            return JsonResponse({"error": "Verification failed"}, status=403)
    
        return HttpResponse(challenge, content_type='text/plain', status=200)
    
    # POST - Processar eventos
    signature = request.headers.get('X-Hub-Signature-256') or request.headers.get('X-Hub-Signature', '')
    is_dev = getattr(settings, 'DEBUG', False)
    app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', '')
    
    if not app_secret and not is_dev:
        logger.error("[Webhook] CRÍTICO: FACEBOOK_APP_SECRET não configurado no .env! Webhook não aceitará mensagens em produção.")
    
    if signature:
        if not verify_webhook_signature(request.body, signature):
            if not is_dev:
                logger.warning(f"[Webhook] Assinatura inválida. Host: {request.get_host()} | Path: {request.path}")
                return JsonResponse({"error": "Invalid signature"}, status=403)
            else:
                logger.info("[Webhook] Assinatura inválida mas ignorada por estar em modo DEBUG.")
    else:
        if not is_dev:
            logger.warning(f"[Webhook] Requisição POST sem assinatura (X-Hub-Signature-256). Host: {request.get_host()}")
            return JsonResponse({"error": "Missing signature"}, status=403)
        else:
            logger.info("[Webhook] Requisição POST sem assinatura mas permitida por estar em modo DEBUG.")
    
    try:
        data = json.loads(request.body)
        
        if data.get("object") != "whatsapp_business_account":
            return JsonResponse({"error": "Invalid object"}, status=400)
        
        entries = data.get("entry", [])
        
        if not entries:
            return JsonResponse({"status": "success"}, status=200)
        
        for entry_idx, entry in enumerate(entries):
            waba_id = entry.get("id")
            changes = entry.get("changes", [])
            
            if not waba_id:
                continue
            
            # Atualizar números de telefone se necessário (compatibilidade)
            canal = Canal.objects.filter(
                tipo="whatsapp_oficial",
                waba_id=waba_id,
                ativo=True
            ).first()
            
            if canal and not canal.phone_number_id and canal.token:
                fetch_and_update_phone_numbers(waba_id, canal)
            
            # Processar cada mudança
            for change in changes:
                field = change.get("field")
                value = change.get("value", {})
                
                # VERIFICAÇÃO ESPECIAL: Se field="messages" e há statuses dentro, processar statuses diretamente
                if field == "messages" and value.get("statuses"):
                    process_message_statuses(waba_id, value)
                    continue  # Não processar como mensagem normal
                
                if not field:
                    continue
                
                # Roteamento por field name
                try:
                    route_webhook_event(field, waba_id, value)
                except Exception as e:
                    # Continuar processando outros eventos
                    logger.error(f"[Webhook] Erro ao processar field {field}: {str(e)}", exc_info=True)
                    pass
        
        return JsonResponse({"status": "success"}, status=200)
    
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": "Internal server error"}, status=500)


def process_message_echoes(waba_id: str, value: dict):
    """Processa mensagens enviadas pelo WhatsApp Business app."""
    try:
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")
        display_phone_number = metadata.get("display_phone_number")
        
        message_echoes = value.get("message_echoes", [])
        
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            phone_number_id=phone_number_id,
            ativo=True
        ).first()
        
        if canal and canal.provedor:
            provedor = canal.provedor
        else:
            whatsapp_integration = WhatsAppIntegration.objects.filter(
                settings__phone_number_id=phone_number_id
            ).first()
            
            if not whatsapp_integration:
                whatsapp_integration = WhatsAppIntegration.objects.filter(
                    phone_number=display_phone_number
                ).first()
            
            if not whatsapp_integration or not whatsapp_integration.provedor:
                return
            
            provedor = whatsapp_integration.provedor
            # Canal necessário para inbox, download de mídia e token da Graph API
            canal = (
                Canal.objects.filter(
                    tipo="whatsapp_oficial",
                    phone_number_id=phone_number_id,
                    provedor=provedor,
                ).first()
                or Canal.objects.filter(
                    tipo="whatsapp_oficial",
                    provedor=provedor,
                    ativo=True,
                ).first()
            )
            if not canal:
                logger.warning(
                    f"[WhatsAppWebhook][Echo] Canal WhatsApp não encontrado "
                    f"(phone_number_id={phone_number_id}, provedor={provedor.id})"
                )
                return
        
        for echo in message_echoes:
            message_id = echo.get("id")
            from_number = echo.get("from")
            to_number = echo.get("to")
            timestamp = echo.get("timestamp")
            message_type = echo.get("type")
            
            normalized_to = normalize_phone_number(to_number)
            
            if not normalized_to:
                continue
            
            contact, _ = Contact.objects.get_or_create(
                phone=normalized_to,
                provedor=provedor,
                defaults={"name": normalized_to}
            )
            
            from conversations.models import Inbox, Team
            # Lógica corrigida: Bucar inbox específico do canal para evitar mistura de mensagens
            inbox = Inbox.objects.filter(
                channel_type='whatsapp_oficial',
                channel_id=str(canal.id),
                provedor=provedor
            ).first()
            
            if not inbox:
                inbox = Inbox.objects.create(
                    channel_type='whatsapp_oficial',
                    provedor=provedor,
                    name=f"WhatsApp - {canal.nome}",
                    channel_id=str(canal.id),
                    is_active=True
                )
            
            # Verificar modo de atendimento
            bot_mode = getattr(provedor, 'bot_mode', 'ia')
            ia_team = None
            if bot_mode == 'ia':
                # Obter ou criar equipe IA automaticamente apenas se estiver no modo IA
                ia_team = Team.get_or_create_ia_team(provedor)
            
            # Criar conversa. No modo chatbot, status é "pending" e não tem equipe IA.
            # Usar filter().first() para evitar MultipleObjectsReturned
            conversation = Conversation.objects.filter(
                contact=contact,
                inbox=inbox
            ).first()
            
            if not conversation:
                conversation = Conversation.objects.create(
                    contact=contact,
                    inbox=inbox,
                    status="snoozed" if bot_mode == 'ia' else "pending",
                    team=ia_team,
                    assignee=None
                )
                conv_created = True
            else:
                conv_created = False
            
            # Se a conversa já existia mas estava fechada ou em closing, reabrir
            if conversation.status in ["closed", "resolved", "finalizada", "closing"]:
                conversation.status = "snoozed" if bot_mode == 'ia' else "pending"
                conversation.team = ia_team
                conversation.assignee = None
                conversation.save()
            
            content = ""
            file_url = None
            file_name = None
            
            if message_type == "text":
                content = echo.get("text", {}).get("body", "")
            elif message_type == "image":
                image_data = echo.get("image", {})
                content = image_data.get("caption", "")
                file_url = image_data.get("id")
                file_name = None  # Será definido pelo download_whatsapp_media usando o ID da mídia
            elif message_type == "audio":
                audio_data = echo.get("audio", {})
                file_url = audio_data.get("id")
                # A extensão será determinada pelo mime_type durante o download
                file_name = None
                content = ""
            elif message_type == "video":
                video_data = echo.get("video", {})
                content = video_data.get("caption", "")
                file_url = video_data.get("id")
                file_name = None
            elif message_type == "document":
                doc_data = echo.get("document", {})
                content = doc_data.get("caption", "")
                file_url = doc_data.get("id")
                file_name = doc_data.get("filename", "document")
            
            existing_message = Message.objects.filter(
                external_id=message_id,
                conversation=conversation
            ).first()
            
            if existing_message:
                continue
            
            additional_attrs_echo = {
                "source": "whatsapp_business_app",
                "waba_id": waba_id,
                "phone_number_id": phone_number_id,
            }
            original_file_name = file_name
            # Eco da Meta traz `id` da mídia, não URL — baixar como nas mensagens recebidas
            if message_type in ["image", "audio", "video", "document"] and file_url and canal:
                try:
                    local_url, meta_saved = download_whatsapp_media(
                        file_url, canal, conversation.id, original_file_name or message_type
                    )
                    if local_url:
                        url_parts = local_url.rstrip("/").split("/")
                        if len(url_parts) >= 2:
                            file_name = url_parts[-1]
                        file_url = local_url
                        if meta_saved:
                            additional_attrs_echo["local_file_url"] = local_url
                            additional_attrs_echo["whatsapp_file_url"] = meta_saved.get(
                                "whatsapp_download_url"
                            )
                            mime_type = meta_saved.get("mime_type")
                            additional_attrs_echo["mime_type"] = mime_type
                            additional_attrs_echo["file_size"] = meta_saved.get("file_size")
                            additional_attrs_echo["sha256"] = meta_saved.get("sha256")
                            if message_type == "audio" and mime_type:
                                if mime_type == "audio/ogg" or "ogg" in mime_type.lower():
                                    additional_attrs_echo["is_voice_message"] = True
                                    additional_attrs_echo["audio_type"] = "voice"
                                else:
                                    additional_attrs_echo["is_voice_message"] = False
                                    additional_attrs_echo["audio_type"] = "basic"
                        logger.info(f"[WhatsAppWebhook][Echo] Mídia baixada: {local_url}")
                    else:
                        logger.warning(
                            f"[WhatsAppWebhook][Echo] Falha ao baixar mídia (media_id={file_url}) "
                            f"conv={conversation.id}"
                        )
                except Exception as e:
                    logger.error(
                        f"[WhatsAppWebhook][Echo] Erro ao baixar mídia: {e}", exc_info=True
                    )
            
            try:
                # Converter timestamp Unix para datetime com timezone do Django (America/Belem)
                # O timestamp da Meta vem em UTC (Unix timestamp)
                # Usar timezone.now() com o timestamp como referência, ou converter corretamente
                from django.utils import timezone as tz
                from datetime import timezone as dt_timezone
                # Criar datetime UTC-aware diretamente usando timezone UTC do datetime
                utc_dt = datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc)
                # Converter para timezone local do Django (America/Belem)
                message_timestamp = utc_dt.astimezone(tz.get_current_timezone())
            except (ValueError, TypeError, Exception) as e:
                logger.warning(f"[WhatsAppWebhook] Erro ao converter timestamp {timestamp}: {e}, usando timezone.now()")
                message_timestamp = timezone.now()
            
            Message.objects.create(
                conversation=conversation,
                content=content or "",
                message_type=message_type,
                is_from_customer=False,
                external_id=message_id,
                file_url=file_url,
                file_name=file_name,
                created_at=message_timestamp,
                additional_attributes=additional_attrs_echo,
            )
    
    except Exception as e:
        logger.exception(f"[WhatsAppWebhook][Echo] Erro ao processar message_echoes: {e}")


def process_history_sync(waba_id: str, value: dict):
    """Processa sincronização de histórico de mensagens."""
    try:
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")
        
        history = value.get("history", [])
        
        if isinstance(history, list) and len(history) > 0:
            errors = history[0].get("errors", [])
            if errors:
                return
        
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            phone_number_id=phone_number_id,
            ativo=True
        ).first()
        
        if canal and canal.provedor:
            provedor = canal.provedor
        else:
            whatsapp_integration = WhatsAppIntegration.objects.filter(
                settings__phone_number_id=phone_number_id
            ).first()
            
            if not whatsapp_integration or not whatsapp_integration.provedor:
                return
            
            provedor = whatsapp_integration.provedor
        
        messages_data = history[0].get("messages", []) if history else []
        
        for msg_data in messages_data:
            message_id = msg_data.get("id")
            from_number = msg_data.get("from")
            to_number = msg_data.get("to")
            timestamp = msg_data.get("timestamp")
            message_type = msg_data.get("type")
            
            normalized_from = normalize_phone_number(from_number)
            normalized_to = normalize_phone_number(to_number)
            
            company_number = None
            if canal and canal.phone_number:
                company_number = normalize_phone_number(canal.phone_number)
            elif whatsapp_integration and whatsapp_integration.phone_number:
                company_number = normalize_phone_number(whatsapp_integration.phone_number)
            
            if not company_number:
                display_phone = metadata.get("display_phone_number")
                if display_phone:
                    company_number = normalize_phone_number(display_phone)
                else:
                    continue
            
            if normalized_from == company_number:
                direction = "outgoing"
                contact_phone = normalized_to
            else:
                direction = "incoming"
                contact_phone = normalized_from
            
            contact, _ = Contact.objects.get_or_create(
                phone=contact_phone,
                provedor=provedor,
                defaults={"name": contact_phone}
            )
            
            from conversations.models import Inbox
            # Lógica corrigida: Bucar inbox específico do canal para evitar mistura de mensagens
            inbox = Inbox.objects.filter(
                channel_type='whatsapp_oficial',
                channel_id=str(canal.id),
                provedor=provedor
            ).first()
            
            if not inbox:
                inbox = Inbox.objects.create(
                    channel_type='whatsapp_oficial',
                    provedor=provedor,
                    name=f"WhatsApp - {canal.nome}",
                    channel_id=str(canal.id),
                    is_active=True
                )
            
            # Usar filter().first() para evitar MultipleObjectsReturned
            conversation = Conversation.objects.select_related('team').filter(
                contact=contact,
                inbox=inbox
            ).first()
            
            if not conversation:
                conversation = Conversation.objects.create(
                    contact=contact,
                    inbox=inbox,
                    status="closed"
                )
            
            content = ""
            file_url = None
            file_name = None
            
            if message_type == "text":
                content = msg_data.get("text", {}).get("body", "")
            elif message_type == "image":
                image_data = msg_data.get("image", {})
                content = image_data.get("caption", "")
                file_url = image_data.get("id")
                file_name = None
            elif message_type == "audio":
                audio_data = msg_data.get("audio", {})
                file_url = audio_data.get("id")
                # A extensão será determinada pelo mime_type durante o download
                file_name = None
                content = ""
            elif message_type == "video":
                video_data = msg_data.get("video", {})
                content = video_data.get("caption", "")
                file_url = video_data.get("id")
                file_name = None
            elif message_type == "document":
                doc_data = msg_data.get("document", {})
                content = doc_data.get("caption", "")
                file_url = doc_data.get("id")
                file_name = doc_data.get("filename", "document")
            
            existing_message = Message.objects.filter(
                external_id=message_id,
                conversation=conversation
            ).first()
            
            if existing_message:
                continue
            
            try:
                # Converter timestamp Unix para datetime com timezone do Django (America/Belem)
                # O timestamp da Meta vem em UTC (Unix timestamp)
                # Usar timezone.now() com o timestamp como referência, ou converter corretamente
                from django.utils import timezone as tz
                from datetime import timezone as dt_timezone
                # Criar datetime UTC-aware diretamente usando timezone UTC do datetime
                utc_dt = datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc)
                # Converter para timezone local do Django (America/Belem)
                message_timestamp = utc_dt.astimezone(tz.get_current_timezone())
            except (ValueError, TypeError, Exception) as e:
                logger.warning(f"[WhatsAppWebhook] Erro ao converter timestamp {timestamp}: {e}, usando timezone.now()")
                message_timestamp = timezone.now()
            
            Message.objects.create(
                conversation=conversation,
                content=content or "",
                message_type=message_type,
                is_from_customer=(direction == "incoming"),
                external_id=message_id,
                file_url=file_url,
                file_name=file_name,
                created_at=message_timestamp,
                additional_attributes={
                    "source": "history_sync",
                    "waba_id": waba_id,
                    "phone_number_id": phone_number_id
                }
            )
    
    except Exception as e:
        pass


def process_state_sync(waba_id: str, value: dict):
    """Processa sincronização de estado (contatos)."""
    try:
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")
        
        state_sync = value.get("state_sync", [])
        
        canal = None
        
        if phone_number_id:
            canal = Canal.objects.filter(
                tipo="whatsapp_oficial",
                phone_number_id=phone_number_id,
                ativo=True
            ).first()
        
        if not canal:
            canal = Canal.objects.filter(
                tipo="whatsapp_oficial",
                waba_id=waba_id,
                ativo=True
            ).first()
        
        if canal and not canal.phone_number_id and canal.token:
            fetch_and_update_phone_numbers(waba_id, canal)
        
        if canal and canal.provedor:
            provedor = canal.provedor
        else:
            whatsapp_integration = WhatsAppIntegration.objects.filter(
                settings__phone_number_id=phone_number_id
            ).first()
            
            if not whatsapp_integration or not whatsapp_integration.provedor:
                return
            
            provedor = whatsapp_integration.provedor
        
        for sync_item in state_sync:
            if sync_item.get("type") != "contact":
                continue
            
            contact_data = sync_item.get("contact", {})
            action = sync_item.get("action")
            phone_number = contact_data.get("phone_number")
            full_name = contact_data.get("full_name")
            first_name = contact_data.get("first_name")
            
            if not phone_number:
                continue
            
            normalized_phone = normalize_phone_number(phone_number)
            
            if action == "add" or action == "edit":
                contact, created = Contact.objects.get_or_create(
                    phone=normalized_phone,
                    provedor=provedor,
                    defaults={"name": full_name or first_name or normalized_phone}
                )
                
                if not created:
                    if full_name or first_name:
                        contact.name = full_name or first_name or contact.name
                        contact.save()
            
            elif action == "remove":
                Contact.objects.filter(
                    phone=normalized_phone,
                    provedor=provedor
                ).update(name=f"{normalized_phone} (removido)")
    
    except Exception as e:
        pass


def process_incoming_messages(waba_id: str, value: dict):
    """Processa mensagens recebidas de clientes."""
    try:
        metadata = value.get("metadata", {})
        phone_number_id = metadata.get("phone_number_id")
        display_phone_number = metadata.get("display_phone_number")
        
        messages = value.get("messages", [])
        
        if not messages:
            return
        
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
        
        if canal and canal.provedor:
            provedor = canal.provedor
        else:
            whatsapp_integration = WhatsAppIntegration.objects.filter(
                settings__phone_number_id=phone_number_id
            ).first()
            
            if not whatsapp_integration:
                whatsapp_integration = WhatsAppIntegration.objects.filter(
                    phone_number=display_phone_number
                ).first()
            
            if not whatsapp_integration or not whatsapp_integration.provedor:
                return
            
            provedor = whatsapp_integration.provedor
        
        # Extrair informações de contatos do webhook (nome e foto de perfil)
        contacts_data = value.get("contacts", [])
        contact_info_map = {}
        if contacts_data:
            for contact_data in contacts_data:
                try:
                    wa_id = contact_data.get("wa_id")
                    profile = contact_data.get("profile", {})
                    contact_name = profile.get("name") if profile else None
                    if wa_id and contact_name:
                        normalized_wa_id = normalize_phone_number(wa_id)
                        if normalized_wa_id:
                            contact_info_map[normalized_wa_id] = {
                                "name": contact_name,
                                "wa_id": wa_id
                            }
                except Exception as e:
                    logger.warning(f"[WhatsAppWebhook] Erro ao processar dados de contato do webhook: {e}")
                    continue
        
        for msg in messages:
            message_id = msg.get("id")
            from_number = msg.get("from")
            timestamp = msg.get("timestamp")
            message_type = msg.get("type")
            
            normalized_from = normalize_phone_number(from_number)
            
            if not normalized_from:
                continue
            
            # Buscar nome do contato do webhook se disponível
            contact_name_from_webhook = None
            if normalized_from in contact_info_map:
                contact_name_from_webhook = contact_info_map[normalized_from].get("name")
            
            # Criar ou atualizar contato com nome do webhook
            contact, created = Contact.objects.get_or_create(
                phone=normalized_from,
                provedor=provedor,
                defaults={"name": contact_name_from_webhook or normalized_from}
            )
            
            # Se o contato já existe mas temos um nome do webhook e o nome atual é apenas o número, atualizar
            if not created and contact_name_from_webhook:
                try:
                    if contact.name == normalized_from or contact.name == from_number:
                        contact.name = contact_name_from_webhook
                        contact.save(update_fields=["name"])
                    elif not contact.name or contact.name.strip() == "":
                        contact.name = contact_name_from_webhook
                        contact.save(update_fields=["name"])
                except Exception as e:
                    logger.warning(f"[WhatsAppWebhook] Erro ao atualizar nome do contato {normalized_from}: {e}")
            
            logger.debug(f"[WhatsAppWebhook] Contato processado: {normalized_from} - Nome: {contact.name}")
            
            from conversations.models import Inbox, Team
            
            # LÓGICA CORRIGIDA: Determinar o inbox correto pelo canal que recebeu a mensagem
            # Isso evita criar dois atendimentos (um por whatsapp_oficial e outro por whatsapp genérico)
            
            inbox = None
            
            # 1. Se temos o phone_number_id, tentar identificar se veio por um canal whatsapp_oficial
            if phone_number_id and canal and canal.phone_number_id == phone_number_id:
                # A mensagem veio pelo mesmo canal (whatsapp_oficial) que identificamos no início
                # Buscar o inbox vinculado a este canal
                inbox = Inbox.objects.filter(
                    channel_type='whatsapp_oficial',
                    channel_id=str(canal.id),
                    provedor=provedor
                ).first()

            # 2. Verificar também se existe uma conversa aberta com este contato em QUALQUER inbox do provedor
            # (para não duplicar quando o agente iniciou por um canal específico e o cliente responde)
            if not inbox:
                # Buscar na conversa existente mais recente deste contato com este provedor qual inbox usar
                from conversations.models import Conversation as Conv
                conv_existente = Conv.objects.filter(
                    contact=contact,
                    inbox__provedor=provedor
                ).exclude(
                    status__in=['closed', 'resolved', 'finalizada']
                ).select_related('inbox').order_by('-created_at').first()
                
                if conv_existente and conv_existente.inbox:
                    inbox = conv_existente.inbox
                    logger.info(f"[WhatsAppWebhook] Reutilizando inbox da conversa existente: {inbox.id} ({inbox.channel_type}) para contato {normalized_from}")

            # 3. Fallback: buscar inbox específico do canal que recebeu
            if not inbox and canal:
                inbox = Inbox.objects.filter(
                    channel_type='whatsapp_oficial',
                    channel_id=str(canal.id),
                    provedor=provedor
                ).first()
                
                if not inbox:
                    inbox = Inbox.objects.create(
                        channel_type='whatsapp_oficial',
                        provedor=provedor,
                        name=f"WhatsApp - {canal.nome}",
                        channel_id=str(canal.id),
                        is_active=True
                    )
            
            # Verificar modo de atendimento
            bot_mode = getattr(provedor, 'bot_mode', 'ia')
            ia_team = None
            if bot_mode == 'ia':
                # Obter ou criar equipe IA automaticamente apenas se estiver no modo IA
                ia_team = Team.get_or_create_ia_team(provedor)
            
            # Criar conversa. No modo chatbot, status é "pending" e não tem equipe IA.
            # Usar filter().first() para evitar MultipleObjectsReturned
            conversation = Conversation.objects.select_related('team').filter(
                contact=contact,
                inbox=inbox
            ).first()
            
            if not conversation:
                conversation = Conversation.objects.create(
                    contact=contact,
                    inbox=inbox,
                    status="snoozed",
                    team=ia_team,       # Atribuir à equipe IA se for modo IA
                    assignee=None       # Sem atendente específico
                )
                conv_created = True
            else:
                conv_created = False
            
            # Se a conversa já existia mas estava fechada ou em closing, reabrir (Reset Completo)
            if conversation.status in ["closed", "resolved", "finalizada", "closing"]:
                now = timezone.now()
                from conversations.message_visibility import mark_conversation_new_bot_session
                # Antes de mudar status: zera memória da IA e marca corte de histórico para o painel
                mark_conversation_new_bot_session(conversation)
                conversation.status = "snoozed"
                conversation.team = ia_team
                conversation.assignee = None
                conversation.waiting_for_agent = False # Bot assume o controle
                conversation.created_at = now # Resetar cronômetro para o painel
                conversation.updated_at = now
                conversation.save()
                
                # Limpar memória do chatbot para reiniciar o fluxo do zero (Resgate)
                import asyncio
                from asgiref.sync import async_to_sync
                try:
                    async_to_sync(redis_memory_service.clear_memory)(
                        provedor.id, conversation.id, "whatsapp", "unknown"
                    )
                    logger.info(f"[WhatsAppWebhook] Reset de memória e tempo para conversa reaberta: {conversation.id}")
                except Exception as e:
                    logger.error(f"[WhatsAppWebhook] Erro ao resetar memória da conversa {conversation.id}: {e}")
            
            content = ""
            file_url = None
            file_name = None
            
            # Preparar additional_attributes ANTES de processar tipos de mensagem
            additional_attrs = {
                "source": "whatsapp_cloud_api",
                "waba_id": waba_id,
                "phone_number_id": phone_number_id
            }
            
            if message_type == "text":
                content = msg.get("text", {}).get("body", "")
            elif message_type == "image":
                image_data = msg.get("image", {})
                content = image_data.get("caption", "")
                file_url = image_data.get("id")
                file_name = None
            elif message_type == "audio":
                audio_data = msg.get("audio", {})
                file_url = audio_data.get("id")
                file_name = None
                content = ""
                # Salvar indicador inicial de que pode ser voz (será confirmado após download)
                additional_attrs["is_audio_message"] = True
            elif message_type == "reaction":
                # Processar reação recebida do cliente
                reaction_data = msg.get("reaction", {})
                target_message_id = reaction_data.get("message_id")
                emoji = reaction_data.get("emoji", "")
                
                if not target_message_id:
                    continue
                
                # Buscar a mensagem original que foi reagida (pode ser mensagem do agente)
                target_message = Message.objects.filter(
                    external_id=target_message_id,
                    conversation=conversation
                ).first()
                
                if target_message:
                    # Reação do cliente recebida via webhook
                    # Se target_message.is_from_customer=False, é reação do cliente em mensagem do agente
                    # Se target_message.is_from_customer=True, é reação do cliente em mensagem do cliente
                    from conversations.models import MessageReaction
                    
                    # Verificar se já existe uma reação para esta mensagem do cliente com o mesmo emoji
                    existing_reaction = MessageReaction.objects.filter(
                        message=target_message,
                        is_from_customer=True,
                        emoji=emoji
                    ).first()
                    
                    if not existing_reaction:
                        # Criar nova reação do cliente
                        MessageReaction.objects.create(
                            message=target_message,
                            emoji=emoji,
                            is_from_customer=True,  # Reação recebida do cliente
                            external_id=message_id,
                            additional_attributes={
                                "target_message_id": target_message_id,
                                "source": "whatsapp_cloud_api",
                                "waba_id": waba_id,
                                "phone_number_id": phone_number_id
                            }
                        )
                        logger.info(f"[WhatsAppWebhook] Reação recebida: {emoji} na mensagem {target_message.id}")
                        
                        # Notificar frontend via WebSocket será feito pelo consumer se necessário
                else:
                    logger.warning(f"[WhatsAppWebhook] Mensagem alvo da reação não encontrada: {target_message_id}")
                
                # Reações não criam novas mensagens, apenas atualizam a mensagem original
                continue
            elif message_type == "video":
                video_data = msg.get("video", {})
                content = video_data.get("caption", "")
                file_url = video_data.get("id")
                file_name = None
            elif message_type == "document":
                doc_data = msg.get("document", {})
                content = doc_data.get("caption", "")
                file_url = doc_data.get("id")
                file_name = doc_data.get("filename", "document")
            elif message_type == "interactive":
                interactive_data = msg.get("interactive", {})
                interactive_type = interactive_data.get("type")
                if interactive_type == "button_reply":
                    reply = interactive_data.get("button_reply", {})
                    button_id = reply.get("id")
                    button_title = reply.get("title")
                    content = button_title
                    additional_attrs["button_id"] = button_id
                    additional_attrs["is_interactive_reply"] = True
                    logger.info(f"[WhatsAppWebhook] Resposta de botão interativo: {button_title} ({button_id})")
                elif interactive_type == "list_reply":
                    reply = interactive_data.get("list_reply", {})
                    button_id = reply.get("id")
                    button_title = reply.get("title")
                    content = button_title
                    additional_attrs["button_id"] = button_id
                    additional_attrs["is_interactive_reply"] = True
                    logger.info(f"[WhatsAppWebhook] Resposta de lista interativa: {button_title} ({button_id})")
            
            logger.info(f"[WhatsAppWebhook] RAW MSG: {json.dumps(msg)}")
            logger.info(f"[WhatsAppWebhook] Mensagem processada: type={message_type}, content='{content}', button_id={additional_attrs.get('button_id')}")
            
            existing_message = Message.objects.filter(
                external_id=message_id,
                conversation=conversation
            ).first()
            
            if existing_message:
                continue
            
            try:
                # Converter timestamp Unix para datetime com timezone do Django (America/Belem)
                # O timestamp da Meta vem em UTC (Unix timestamp)
                # Usar timezone.now() com o timestamp como referência, ou converter corretamente
                from django.utils import timezone as tz
                from datetime import timezone as dt_timezone
                # Criar datetime UTC-aware diretamente usando timezone UTC do datetime
                utc_dt = datetime.fromtimestamp(int(timestamp), tz=dt_timezone.utc)
                # Converter para timezone local do Django (America/Belem)
                message_timestamp = utc_dt.astimezone(tz.get_current_timezone())
            except (ValueError, TypeError, Exception) as e:
                logger.warning(f"[WhatsAppWebhook] Erro ao converter timestamp {timestamp}: {e}, usando timezone.now()")
                message_timestamp = timezone.now()
            
            # Verificar se é uma resposta contextual (reply)
            context_data = msg.get("context", {})
            # A Meta usa "id" no context, não "message_id"
            context_message_id = context_data.get("id") if context_data else None
            reply_to_message_id = None
            reply_to_content = None
            
            if context_data:
                logger.info(f"[WhatsAppWebhook] Context data encontrado: {context_data}")
            
            if context_message_id:
                logger.info(f"[WhatsAppWebhook] Resposta contextual detectada - context_message_id (wamid): {context_message_id}")
                # Buscar a mensagem original (wamid em external_id ou em additional_attributes legado)
                original_message = (
                    Message.objects.filter(conversation=conversation)
                    .filter(
                        Q(external_id=context_message_id)
                        | Q(additional_attributes__external_id=context_message_id)
                        | Q(additional_attributes__whatsapp_message_id=context_message_id)
                    )
                    .order_by("-id")
                    .first()
                )
                
                if original_message:
                    reply_to_message_id = original_message.id
                    # Limpar o conteúdo removendo formatações de assinatura do agente (*Nome disse:*)
                    import re
                    reply_to_content = original_message.content
                    # Remover formatações como "*Nome disse:*" ou "**Nome disse:**"
                    reply_to_content = re.sub(r'^\s*\*{1,2}.*?disse:\*{0,2}\s*\n*', '', reply_to_content, flags=re.IGNORECASE | re.MULTILINE)
                    # Remover nome formatado em negrito no início (ex: *Nome*\n\n)
                    reply_to_content = re.sub(r'^\s*\*{1,2}[^*]+\*{1,2}\s*\n+\s*', '', reply_to_content, flags=re.MULTILINE)
                    reply_to_content = reply_to_content.strip()
                    logger.info(f"[WhatsAppWebhook] Mensagem original encontrada: mensagem {message_id} responde a {context_message_id} (local ID: {reply_to_message_id}, conteúdo limpo: {reply_to_content[:50] if reply_to_content else 'N/A'})")
                else:
                    logger.warning(f"[WhatsAppWebhook] Mensagem original não encontrada para context_message_id (wamid): {context_message_id} na conversa {conversation.id}")
            
            # additional_attrs já foi inicializado acima, apenas adicionar informações de reply se houver
            
            # Adicionar informações de reply se houver
            if reply_to_message_id:
                additional_attrs['reply_to_message_id'] = reply_to_message_id
                additional_attrs['reply_to_content'] = reply_to_content
                additional_attrs['reply_to_external_id'] = context_message_id
                additional_attrs['is_reply'] = True
            
            # IMPORTANTE: Baixar mídia ANTES de criar a mensagem para evitar que o frontend receba mensagem sem file_url correto
            # Guardar file_name original antes de ser modificado
            original_file_name = file_name
            local_url = None
            meta_saved = None
            
            # Se for mídia, fazer download ANTES de criar a mensagem
            if message_type in ["image", "audio", "video", "document"] and file_url and canal:
                try:
                    local_url, meta_saved = download_whatsapp_media(file_url, canal, conversation.id, original_file_name or message_type)
                    if local_url:
                        # IMPORTANTE: Extrair o filename real do arquivo salvo da URL local
                        # local_url tem formato: /api/media/messages/{conversation_id}/{filename}/
                        # Precisamos extrair o filename para usar como file_name da mensagem
                        import os
                        url_parts = local_url.rstrip('/').split('/')
                        if len(url_parts) >= 2:
                            downloaded_filename = url_parts[-1]  # Último elemento após a barra final
                            # Usar o filename do arquivo baixado como file_name da mensagem
                            # Isso garante que o nome exibido no frontend seja o nome real do arquivo
                            file_name = downloaded_filename
                            logger.info(f"[WhatsAppWebhook] Filename atualizado para o nome real do arquivo: {file_name}")
                        
                        # Usar local_url como file_url para a mensagem
                        file_url = local_url
                        
                        # Adicionar metadados aos additional_attributes
                        if meta_saved:
                            attrs = dict(additional_attrs) if additional_attrs else {}
                            attrs["local_file_url"] = local_url
                            attrs["whatsapp_file_url"] = meta_saved.get("whatsapp_download_url")
                            mime_type = meta_saved.get("mime_type")
                            attrs["mime_type"] = mime_type
                            attrs["file_size"] = meta_saved.get("file_size")
                            attrs["sha256"] = meta_saved.get("sha256")
                            
                            # Detectar se é mensagem de voz baseado no mime_type
                            # Mensagens de voz da Meta são audio/ogg com codec OPUS
                            if message_type == "audio" and mime_type:
                                if mime_type == "audio/ogg" or "ogg" in mime_type.lower():
                                    attrs["is_voice_message"] = True
                                    attrs["audio_type"] = "voice"  # Para frontend distinguir voz de áudio básico
                                else:
                                    attrs["is_voice_message"] = False
                                    attrs["audio_type"] = "basic"  # Áudio básico (MP3, AAC, etc.)
                            
                            additional_attrs = attrs
                        
                        logger.info(f"[WhatsAppWebhook] Mídia baixada e salva: {local_url} antes de criar mensagem")
                    else:
                        logger.warning(f"[WhatsAppWebhook] Falha ao baixar mídia {file_url} antes de criar mensagem")
                except Exception as e:
                    logger.error(f"[WhatsAppWebhook] Erro ao baixar mídia {file_url}: {e}", exc_info=True)
            
            # Criar mensagem APÓS o download estar completo (se for mídia)
            # Dessa forma, o file_url já está correto quando a mensagem é salva e o signal é disparado
            message_obj = Message.objects.create(
                conversation=conversation,
                content=content or "",
                message_type=message_type,
                is_from_customer=True,
                external_id=message_id,
                file_url=file_url,  # Já será local_url se o download foi bem-sucedido
                file_name=file_name,
                created_at=message_timestamp,
                additional_attributes=additional_attrs
            )
            
            # IMPORTANTE: Fazer refresh antes de enviar via WebSocket para garantir dados atualizados (incluindo reply)
            message_obj.refresh_from_db()
            
            # ==========================================================
            # SALVAR MENSAGEM NO REDIS PARA MEMÓRIA DA IA
            # ==========================================================
            # IMPORTANTE: Salvar mensagem no Redis para que a IA possa acessar o histórico
            if content and message_obj.is_from_customer:
                try:
                    # Centralizado: usar o service único que gerencia o isolamento
                    redis_memory_service.add_message_to_conversation_sync(
                        provedor_id=provedor.id,
                        conversation_id=conversation.id,
                        sender='customer',
                        content=content,
                        channel='whatsapp', # Sempre canal por extenso
                        phone=contact.phone
                    )
                except Exception as e:
                    logger.warning(f"[WhatsAppWebhook] Erro ao salvar mensagem no Redis: {e}")
            
            # Atualizar last_message_at da conversa para aparecer no topo da lista
            # IMPORTANTE: Usar o timestamp da mensagem já convertido para timezone aware
            # Isso garante que a hora está correta (usando timezone do Django: America/Belem)
            message_timestamp_obj = message_timestamp if message_timestamp else timezone.now()
            conversation.last_message_at = message_timestamp_obj
            # IMPORTANTE: Atualizar last_user_message_at quando mensagem vier do cliente
            # Isso é usado para calcular a janela de 24 horas no WhatsApp Official
            # O timestamp já está no timezone correto (America/Belem)
            is_customer_message = message_obj.is_from_customer
            if is_customer_message:
                conversation.last_user_message_at = message_timestamp_obj
                conversation.save(update_fields=['last_message_at', 'last_user_message_at'])
            else:
                conversation.save(update_fields=['last_message_at'])
            
            # Notificar frontend via WebSocket (igual Telegram/Uazapi)
            try:
                # Usar o serializer para garantir que todos os campos sejam incluídos
                from conversations.serializers import MessageSerializer, ConversationSerializer
                serializer = MessageSerializer(message_obj)
                message_data = serializer.data
                
                # Adicionar campos adicionais que podem ser úteis
                message_data['contact_name'] = contact.name
                message_data['contact_phone'] = contact.phone
                
                # Se a mensagem é do cliente, também enviar a conversa atualizada com status da janela de 24h
                conversation_data = None
                if is_customer_message:
                    # IMPORTANTE: Fazer refresh da conversa DEPOIS do save para garantir que last_user_message_at está atualizado
                    # O refresh_from_db() busca os dados mais recentes do banco
                    conversation.refresh_from_db()
                    # Serializar conversa atualizada (inclui is_24h_window_open calculado)
                    conversation_serializer = ConversationSerializer(conversation)
                    conversation_data = conversation_serializer.data
                    logger.info(f"[WhatsAppWebhook] Conversa atualizada enviada: is_24h_window_open={conversation_data.get('is_24h_window_open')}, last_user_message_at={conversation_data.get('last_user_message_at')}")
                
                # A notificação agora é feita via signal (post_save no modelo Message)
                # para garantir que todas as fontes de mensagem (WhatsApp, Telegram, Manual)
                # acionem a ordenação no dashboard em tempo real.
                logger.debug(f"[WhatsAppWebhook] Mensagem salva, notificação via signal disparada")
                
            except Exception as e:
                logger.error(f"[WhatsAppWebhook] Erro ao salvar mensagem ou processar: {e}", exc_info=True)
                pass
            
            # ==========================================================
            # CHATBOT ENGINE / ROUTING LOGIC (UPDATED)
            # ==========================================================
            # Verificar o modo de atendimento do provedor
            bot_mode = getattr(provedor, 'bot_mode', 'ia')
            chatbot_handled = False
            
            if is_customer_message:
                # Bloqueio financeiro: não permitir IA/Chatbot para provedor inativo
                if not getattr(provedor, 'is_active', True):
                    logger.info(
                        f"[WhatsAppWebhook] IA/Chatbot suprimidos para provedor {provedor.id}: "
                        f"provedor inativo. Motivo: {getattr(provedor, 'block_reason', '')}"
                    )
                    chatbot_handled = False
                # VERIFICAR SE O CANAL TEM IA/CHATBOT ATIVA
                elif canal and not canal.ia_ativa:
                    logger.info(f"[WhatsAppWebhook] ChatBot suprimido para o canal {canal.id} ({canal.nome}): ia_ativa=False")
                    chatbot_handled = False
                elif bot_mode == 'chatbot':
                    # VERIFICAR SUPRESSÃO DO CHATBOT (Atribuído, Status Ativo ou Transferido para Equipe Humana)
                    is_assigned = conversation.assignee_id is not None
                    is_active_agent_status = conversation.status in ['open', 'pending', 'closed', 'closing']
                    # Só suprimir por equipe se não for a equipe "IA"
                    if is_assigned or is_active_agent_status:
                        logger.info(f"[WhatsAppWebhook] ChatbotEngine suprimido para conversa {conversation.id}: atribuída (assignee_id={conversation.assignee_id}) ou status ativo/fila (status={conversation.status}).")
                        chatbot_handled = False
                    else:
                        # Verificar se o contato está bloqueado para atendimento (toggle ATENDER desativado)
                        contact_bloqueado = getattr(contact, 'bloqueado_atender', False) if contact else False
                        if contact_bloqueado:
                            logger.info(f"[WhatsAppWebhook] ChatbotEngine suprimido para conversa {conversation.id}: contato {contact.phone} está BLOQUEADO para atendimento (ATENDER=OFF)")
                            chatbot_handled = False
                        else:
                            logger.info(f"[WhatsAppWebhook] Provador {provedor.id} em modo CHATBOT. Invocando ChatbotEngine.")
                            try:
                                from asgiref.sync import async_to_sync
                                async def run_chatbot_engine():
                                    from asgiref.sync import sync_to_async
                                    # Obter instância do canal de forma segura em contexto async
                                    canal = await sync_to_async(inbox.get_canal_instance)()
                                    canal_id = canal.id if canal else None
                                    return await ChatbotEngine.process_message(
                                        provedor_id=provedor.id,
                                        conversation_id=conversation.id,
                                        message_content=content or "",
                                        button_id=additional_attrs.get("button_id"),
                                        canal_id=canal_id
                                    )
                                
                                # Sempre tenta processar pelo chatbot se estiver no modo chatbot
                                result = async_to_sync(run_chatbot_engine)()
                                chatbot_handled = result[0] if isinstance(result, tuple) else result
                                if chatbot_handled:
                                    logger.info(f"[WhatsAppWebhook] Mensagem processada pelo Chatbot Engine na conversa {conversation.id}: {result[1] if isinstance(result, tuple) else ''}")
                                else:
                                    logger.warning(f"[WhatsAppWebhook] Provedor em modo CHATBOT mas nenhum nó foi executado para a conversa {conversation.id}: {result[1] if isinstance(result, tuple) else ''}")
                            except Exception as chatbot_err:
                                logger.error(f"[WhatsAppWebhook] Erro ao invocar Chatbot Engine: {chatbot_err}", exc_info=True)
                else:
                    # Se estiver em modo IA, ainda podemos tentar o chatbot como fallback ou se já houver um fluxo iniciado?
                    # Por simplicidade e seguindo a solicitação de "bot_mode", se for IA, pulamos o chatbot aqui.
                    logger.debug(f"[WhatsAppWebhook] Provedor {provedor.id} em modo IA. Pulando ChatbotEngine.")

            # ==========================================================
            # VERIFICAR CSAT ANTES DE CHAMAR IA (WhatsApp Official)
            # ==========================================================
            # IMPORTANTE: Se o chatbot tratou OU se estamos em modo chatbot, não chamamos IA
            csat_processed = chatbot_handled or (bot_mode == 'chatbot')
            if not csat_processed and content and message_type == "text" and message_obj.is_from_customer:
                try:
                    from conversations.models import CSATRequest
                    from conversations.csat_automation import CSATAutomationService
                    
                    # Verificar se há CSATRequest pendente (status 'sent')
                    csat_pendente = CSATRequest.objects.filter(
                        conversation=conversation,
                        contact=contact,
                        status='sent'
                    ).first()
                    
                    if csat_pendente:
                        logger.info(f"[WhatsAppWebhook] CSATRequest pendente encontrado para conversa {conversation.id}, processando resposta CSAT")
                        
                        # Processar resposta CSAT
                        csat_feedback = CSATAutomationService.process_csat_response(
                            message_text=str(content),
                            conversation=conversation,
                            contact=contact
                        )
                        
                        if csat_feedback:
                            # CSAT processado com sucesso
                            csat_processed = True
                            logger.info(f"[WhatsAppWebhook] CSAT processado com sucesso - rating={csat_feedback.rating_value} ({csat_feedback.emoji_rating})")
                            
                            # Garantir que conversa permaneça fechada (não reabrir)
                            if conversation.status != 'closed':
                                conversation.status = 'closed'
                                conversation.save(update_fields=['status'])
                            
                            # Migrar histórico para Supabase APÓS receber feedback CSAT
                            try:
                                from core.chat_migration_service import chat_migration_service
                                migration_result = chat_migration_service.encerrar_e_migrar(
                                    conversation_id=conversation.id,
                                    metadata={
                                        'migrado_apos_csat': True,
                                        'csat_feedback_id': csat_feedback.id,
                                        'rating': csat_feedback.rating_value
                                    }
                                )
                                if migration_result.get('success'):
                                    logger.info(f"[WhatsAppWebhook] Histórico migrado para Supabase após feedback CSAT - conversa {conversation.id}")
                                else:
                                    logger.warning(f"[WhatsAppWebhook] Falha ao migrar histórico após CSAT: {migration_result.get('errors', [])}")
                            except Exception as migration_err:
                                logger.error(f"[WhatsAppWebhook] Erro ao migrar histórico após CSAT: {migration_err}", exc_info=True)
                            
                            # Não chamar IA - apenas processar CSAT e agradecer
                            logger.info(f"[WhatsAppWebhook] CSAT processado - IA não será chamada para conversa {conversation.id}")
                        else:
                            logger.warning(f"[WhatsAppWebhook] Falha ao processar resposta CSAT para conversa {conversation.id}")
                except Exception as csat_err:
                    logger.error(f"[WhatsAppWebhook] Erro ao verificar/processar CSAT: {csat_err}", exc_info=True)
            
            # ==========================================================
            # CHAMAR IA PARA RESPONDER AUTOMATICAMENTE (WhatsApp Official)
            # ==========================================================
            # Processar apenas mensagens de texto do cliente
            # IMPORTANTE: Não chamar IA se CSAT foi processado
            # IMPORTANTE: Áudios não são processados pela IA (apenas exibidos no chat)
            # IMPORTANTE: Não chamar IA se IA estiver desativada no canal
            canal_ia_ativa = canal.ia_ativa if canal else True
            
            should_call_ai = (
                not csat_processed 
                and content 
                and message_obj.is_from_customer 
                and message_type == "text"  # Apenas mensagens de texto
                and canal_ia_ativa  # Apenas se a IA estiver ativa no canal
                and getattr(provedor, 'is_active', True)  # Apenas se o provedor estiver ativo
            )
            
            if not canal_ia_ativa:
                logger.info(f"[WhatsAppWebhook] Chamada da IA suprimida para o canal {canal.id if canal else 'N/A'}: ia_ativa=False")

            if should_call_ai:
                logger.info(f"[WhatsAppWebhook] Verificando se deve chamar IA - content={bool(content)}, message_type={message_type}, is_from_customer={message_obj.is_from_customer}")
                logger.info(f"[WhatsAppWebhook] Condições satisfeitas, iniciando chamada da IA para conversa {conversation.id}")
                # Chamar IA em background usando threading para não bloquear o webhook
                # IMPORTANTE: Criar novo event loop na thread para evitar "Event loop is closed"
                import threading
                import asyncio
                
                def call_ai_in_thread():
                    try:
                        logger.info(f"[WhatsAppWebhook] Thread da IA iniciada para conversa {conversation.id}")
                        # Criar novo event loop para esta thread
                        # Isso é necessário porque async_to_sync precisa de um event loop ativo
                        # Quando executado em thread, não há event loop, então criamos um novo
                        try:
                            # Tentar obter event loop existente
                            loop = asyncio.get_event_loop()
                            if loop.is_closed():
                                raise RuntimeError("Loop is closed")
                        except RuntimeError:
                            # Se não houver loop ou estiver fechado, criar um novo
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        
                        logger.info(f"[WhatsAppWebhook] Chamando IA para conversa {conversation.id}, contato {contact.phone}")
                        # Executar a função que chama a IA
                        # async_to_sync vai usar o loop que acabamos de criar
                        call_ai_and_respond_whatsapp(
                            conversation, contact, provedor, content, message_id, canal
                        )
                        logger.info(f"[WhatsAppWebhook] IA processada para conversa {conversation.id}")
                    except Exception as e:
                        logger.error(f"[WhatsAppWebhook] Erro ao chamar IA na thread: {e}", exc_info=True)
                
                # Executar em thread separada para não bloquear o webhook
                thread = threading.Thread(target=call_ai_in_thread, daemon=True)
                thread.start()
                logger.info(f"[WhatsAppWebhook] Thread da IA iniciada para conversa {conversation.id}")
            elif csat_processed:
                if bot_mode == 'chatbot':
                    logger.info(f"[WhatsAppWebhook] IA não será chamada - Modo Chatbot está ativo para conversa {conversation.id}")
                else:
                    logger.info(f"[WhatsAppWebhook] IA não será chamada - CSAT foi processado para conversa {conversation.id}")
            else:
                logger.info(f"[WhatsAppWebhook] IA não será chamada - content={bool(content)}, message_type={message_type}, is_from_customer={message_obj.is_from_customer}")
    
    except Exception as e:
        logger.error(f"[WhatsAppWebhook] Erro ao processar mensagem: {e}", exc_info=True)
        pass


def call_ai_and_respond_whatsapp(conversation, contact, provedor, content: str, reply_to_message_id: str, canal):
    """
    Chama a IA e envia a resposta automaticamente no WhatsApp Official.
    Similar ao call_ai_and_respond do Telegram, mas adaptado para WhatsApp Cloud API.
    
    IMPORTANTE: Esta função garante isolamento por provedor, conversa e contato para evitar
    que a IA responda para outro cliente.
    """
    try:
        logger.info(f"[WhatsAppWebhook] call_ai_and_respond_whatsapp chamada - conversa {conversation.id}, status={conversation.status}, assignee_id={conversation.assignee_id}")
        
        # 1. Verificações de Elegibilidade da IA
        # A IA deve responder quando:
        # - A conversa NÃO está atribuída (assignee is None)
        # - A conversa NÃO está em 'pending', 'closed', ou 'closing'
        # - Pode estar em 'open' ou 'snoozed'
        if conversation.assignee_id or conversation.status in ['pending', 'closed', 'closing']:
            logger.info(f"[WhatsAppWebhook] IA ignorada: conversa {conversation.id} está atribuída (assignee_id={conversation.assignee_id}) ou em status inválido (status={conversation.status}).")
            return
        
        if contact and getattr(contact, 'bloqueado_atender', False):
            logger.info(f"[WhatsAppWebhook] IA ignorada: contato {contact.phone} está bloqueado.")
            return
        
        if not provedor:
            logger.warning(f"[WhatsAppWebhook] IA ignorada: provedor não encontrado.")
            return
        
        # Bloqueio financeiro: provedor inativo não pode receber respostas da IA
        if not getattr(provedor, 'is_active', True):
            logger.info(
                f"[WhatsAppWebhook] IA ignorada: provedor {provedor.id} inativo. "
                f"Motivo: {getattr(provedor, 'block_reason', '')}"
            )
            return

        # Verificar se a IA está ativa no canal
        from core.models import Canal
        canal_obj = None
        # O parâmetro 'canal' pode ser um objeto Canal ou None
        if canal and isinstance(canal, Canal):
            canal_obj = canal
        else:
            # Tentar buscar canal pelo channel_id do inbox
            if conversation.inbox.channel_id and conversation.inbox.channel_id != 'default':
                try:
                    canal_obj = Canal.objects.filter(
                        id=conversation.inbox.channel_id,
                        provedor=provedor
                    ).first()
                except (ValueError, TypeError):
                    pass
            
            # Se não encontrou pelo channel_id, buscar pelo tipo do canal
            if not canal_obj:
                channel_type = conversation.inbox.channel_type
                if channel_type == 'whatsapp_oficial':
                    canal_obj = Canal.objects.filter(
                        provedor=provedor,
                        tipo='whatsapp_oficial',
                        ativo=True
                    ).first()
        
        # Se encontrou o canal e a IA está desativada, não chamar IA
        if canal_obj and not canal_obj.ia_ativa:
            logger.info(f"[WhatsAppWebhook] IA NÃO chamada - canal {canal_obj.id} ({canal_obj.nome}) tem IA desativada (ia_ativa=False)")
            return
        
        # 2. Chamar Orquestrador de IA (Mestre)
        from core.openai_service import openai_service
        
        # Contexto forte para a IA
        contexto = {
            'conversation': conversation,
            'contact': contact,
            'canal': 'whatsapp', # Sempre canal por extenso
            'provedor_id': provedor.id,
            'conversation_id': conversation.id,
            'contact_phone': contact.phone
        }
        
        # 2.1 Indicador de Digitação (Início)
        try:
            from integrations.whatsapp_cloud_send import send_typing_indicator
            # Usar canal_obj já obtido acima, ou buscar novamente se necessário
            if not canal_obj:
                canal_obj = Canal.objects.filter(provedor=provedor, tipo="whatsapp_oficial", ativo=True).first()
            if canal_obj and reply_to_message_id:
                send_typing_indicator(canal_obj, reply_to_message_id)
        except Exception:
            pass

        # Chamar a IA (bloqueante na thread, mas em background no webhook)
        ia_result = openai_service.generate_response_sync(
            mensagem=content,
            provedor=provedor,
            contexto=contexto
        )
        
        if not ia_result.get('success'):
            motivo = ia_result.get('motivo', ia_result.get('erro', 'desconhecido'))
            if motivo == "IA_BUSY":
                logger.info(f"[WhatsAppWebhook] IA já em execução para conversa {conversation.id}. Evitando duplicidade.")
            else:
                logger.warning(f"[WhatsAppWebhook] Falha na IA para conversa {conversation.id}: {motivo}")
            return
        
        resposta_ia = ia_result.get('resposta')
        if not resposta_ia:
            logger.warning(f"[WhatsAppWebhook] IA retornou resposta vazia para {conversation.id}")
            return
        
        # 🚨 SEGURANÇA CRÍTICA: Remover qualquer código antes de enviar ao cliente
        from core.ai_response_formatter import AIResponseFormatter
        formatter = AIResponseFormatter()
        resposta_ia = formatter.remover_exposicao_funcoes(resposta_ia)
        
        # 3. Formatação WhatsApp (Markdown compatível)
        import re
        resposta_ia = re.sub(r'\*\*([^*]+?)\*\*', r'*\1*', resposta_ia)
        
        # 3.1 Delay (Simulação de Humanidade)
        try:
            import time
            # Delay proporcional ao tamanho da resposta (1s para cada 60 caracteres, min 1.5s, max 5s)
            delay = min(max(len(resposta_ia) / 60, 1.5), 5)
            logger.info(f"[WhatsAppWebhook] Aplicando delay de {delay:.1f}s para simular digitação.")
            time.sleep(delay)
        except Exception as e:
            logger.warning(f"[WhatsAppWebhook] Erro ao aplicar delay: {e}")

        # 4. Enviar via WhatsApp Cloud API
        from integrations.whatsapp_cloud_send import send_via_whatsapp_cloud_api
        
        success, response = send_via_whatsapp_cloud_api(
            conversation=conversation,
            content=resposta_ia,
            message_type='text'
        )
        
        if not success:
            logger.error(f"[WhatsAppWebhook] Erro ao enviar resposta IA {conversation.id}: {response}")
            return
        
        # Extrair external_id
        external_id = None
        if isinstance(response, dict):
            msgs = response.get('messages', [])
            if msgs: external_id = msgs[0].get('id')
        
        # 5. Salvar Mensagem e Atualizar Memória
        ai_message = Message.objects.create(
            conversation=conversation,
            content=resposta_ia,
            message_type='text',
            is_from_customer=False,
            external_id=external_id,
            additional_attributes={
                'is_ai_response': True,
                'from_ai': True,
                'ai_conversation_id': ia_result.get('ai_conversation_id'),
                'source': 'whatsapp_cloud_api'
            }
        )
        
        # Salvar resposta da IA no Redis
        redis_memory_service.add_message_to_conversation_sync(
            provedor_id=provedor.id,
            conversation_id=conversation.id,
            sender='ai',
            content=resposta_ia,
            channel='whatsapp',
            phone=contact.phone
        )
        
        # Mudar status para 'snoozed' (IA no comando)
        if conversation.status == 'pending':
            conversation.status = 'snoozed'
            conversation.save(update_fields=['status'])
            
        logger.info(f"[WhatsAppWebhook] IA respondeu com sucesso para {conversation.id} (ai_id: {ia_result.get('ai_conversation_id')})")
        
    except Exception as e:
        logger.error(f"[WhatsAppWebhook] Erro fatal no fluxo IA: {e}", exc_info=True)


def process_phone_number_update(waba_id: str, value: dict):
    """Processa atualizações de número de telefone."""
    try:
        canal = Canal.objects.filter(
            tipo="whatsapp_oficial",
            waba_id=waba_id,
            ativo=True
        ).first()
        
        if not canal:
            return
        
        fetch_and_update_phone_numbers(waba_id, canal)
    
    except Exception as e:
        pass


def process_template_status_update(waba_id: str, value: dict):
    """Processa atualizações de status de templates."""
    pass


def process_template_components_update(waba_id: str, value: dict):
    """Processa atualizações de componentes de templates."""
    pass
