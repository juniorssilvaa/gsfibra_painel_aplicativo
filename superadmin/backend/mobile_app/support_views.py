"""Canal de atendimento do app mobile (gateway Superadmin ↔ painel do provedor)."""
from __future__ import annotations

import logging
import re
from typing import Optional

from django.http import FileResponse, Http404
from django.utils.encoding import smart_str
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from super_core.models import Provedor

from .models import MobileAppUser, MobileSupportMedia
from .public_api import _require_provedor
from .push_service import send_push_notification_core
from .tenant_bridge import get_tenant_app_mobile_messages, post_tenant_app_mobile

logger = logging.getLogger(__name__)


def _digits(value) -> str:
    return re.sub(r'\D', '', str(value or ''))


def _public_origin(request) -> str:
    proto = request.META.get('HTTP_X_FORWARDED_PROTO') or request.scheme or 'https'
    host = request.META.get('HTTP_X_FORWARDED_HOST') or request.get_host()
    return f'{proto}://{host}'.rstrip('/')


def _media_public_url(request, media: MobileSupportMedia) -> str:
    return f'{_public_origin(request)}/v1/support/files/{media.id}/'


def _save_uploaded_media(request, provedor, cpf: str):
    upload = request.FILES.get('file') or request.FILES.get('media')
    if not upload:
        return None, None
    media = MobileSupportMedia.objects.create(
        provedor=provedor,
        cpf=cpf,
        file=upload,
        content_type=(getattr(upload, 'content_type', None) or '')[:120],
        original_name=(getattr(upload, 'name', None) or '')[:255],
    )
    return media, _media_public_url(request, media)


def _guess_message_type(explicit: str, media: Optional[MobileSupportMedia], content_type: str) -> str:
    explicit = (explicit or '').strip().lower()
    if explicit in ('text', 'image', 'audio', 'video', 'document', 'ptt', 'sticker', 'location'):
        return explicit
    mime = (content_type or (media.content_type if media else '') or '').lower()
    if mime.startswith('image/'):
        return 'image'
    if mime.startswith('audio/'):
        return 'audio'
    if mime.startswith('video/'):
        return 'video'
    if mime:
        return 'document'
    return 'text'


def _resolve_app_user(provedor, cpf: str):
    return (
        MobileAppUser.objects.filter(provedor=provedor, cpf=cpf).first()
        or MobileAppUser.objects.filter(provedor=provedor, cpf__endswith=cpf[-11:] if len(cpf) >= 11 else cpf).first()
    )


def _require_integration_provedor(request):
    auth = request.META.get('HTTP_AUTHORIZATION', '')
    token = ''
    if auth.startswith('Bearer '):
        token = auth.split(' ', 1)[1].strip()
    if not token:
        token = (
            request.META.get('HTTP_X_PROVIDER_TOKEN', '')
            or request.query_params.get('integration_token')
            or ''
        ).strip()
    if not token:
        return None, Response({'error': 'Token de integração obrigatório.'}, status=401)
    provedor = Provedor.objects.filter(integration_token=token).first()
    if not provedor:
        return None, Response({'error': 'Token de integração inválido.'}, status=401)
    return provedor, None


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([JSONParser, FormParser])
def verify_app_token(request):
    """
    Painel do provedor valida o sk_live_* colado em Integrações.
    Header: Authorization: Bearer <integration_token>
    Body: { "token": "sk_live_..." }
    """
    provedor, err = _require_integration_provedor(request)
    if err:
        return err

    app_token = (
        request.data.get('token')
        or request.data.get('app_token')
        or request.data.get('provider_token')
        or ''
    ).strip()
    if not app_token.startswith('sk_live_'):
        return Response(
            {'valid': False, 'error': 'Informe o token sk_live_ gerado no painel do app.'},
            status=400,
        )

    from .services import resolve_provedor_from_provider_token

    token_provedor = resolve_provedor_from_provider_token(app_token, require_active=False)
    if not token_provedor or token_provedor.id != provedor.id:
        return Response(
            {
                'valid': False,
                'error': 'Token inválido ou de outro provedor. Use o sk_live_ do painel do app deste provedor.',
            },
            status=403,
        )

    suffix = app_token[-8:] if len(app_token) >= 8 else app_token
    return Response({
        'valid': True,
        'provedor_id': provedor.id,
        'token_suffix': suffix,
    })


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def support_messages(request):
    """
    App do cliente:
      GET  /v1/support/messages/?provider_token=&cpf=&after_id=
      POST /v1/support/messages/  {provider_token, cpf, content, message_type} + file
    """
    ctx, err = _require_provedor(request, from_body=request.method == 'POST')
    if err:
        return err
    provedor, profile = ctx

    cpf = _digits(
        request.query_params.get('cpf')
        or (request.data.get('cpf') if request.method != 'GET' else None)
        or ''
    )
    if not cpf:
        return Response({'error': 'cpf é obrigatório.'}, status=400)

    if request.method == 'GET':
        after_id = request.query_params.get('after_id') or None
        ok, error, body = get_tenant_app_mobile_messages(provedor, cpf, after_id=after_id)
        if not ok:
            return Response({'error': error or 'Falha ao carregar mensagens.'}, status=502)
        return Response(body if isinstance(body, dict) else {'messages': body or []})

    content = (request.data.get('content') or request.data.get('message') or '').strip()
    media, file_url = _save_uploaded_media(request, provedor, cpf)
    message_type = _guess_message_type(
        request.data.get('message_type') or request.data.get('media_type'),
        media,
        request.data.get('mime_type') or '',
    )
    if not content and not file_url:
        return Response({'error': 'Envie texto ou um arquivo.'}, status=400)

    app_user = _resolve_app_user(provedor, cpf)
    payload = {
        'cpf': cpf,
        'name': (app_user.name if app_user else '') or request.data.get('name') or '',
        'email': (app_user.email if app_user else '') or '',
        'content': content,
        'message_type': message_type,
        'file_url': file_url or '',
        'file_name': (media.original_name if media else '') or '',
        'mime_type': (media.content_type if media else '') or '',
        'provedor_id': provedor.id,
        'provider_name': provedor.nome or '',
        'app_default_team_id': profile.app_default_team_id or '',
    }

    ok, error, body = post_tenant_app_mobile(provedor, payload)
    if not ok:
        return Response({'error': error or 'Falha ao enviar mensagem ao atendimento.'}, status=502)
    return Response(body if isinstance(body, dict) else {'success': True}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([JSONParser, MultiPartParser, FormParser])
def support_outbound(request):
    """
    Painel do provedor → cliente no app.
    POST /v1/support/outbound/
    Header: Authorization: Bearer <integration_token>
    """
    provedor, err = _require_integration_provedor(request)
    if err:
        return err

    cpf = _digits(request.data.get('cpf') or request.data.get('customer_id') or '')
    if not cpf:
        return Response({'error': 'cpf é obrigatório.'}, status=400)

    content = (request.data.get('content') or request.data.get('message') or '').strip()
    media, file_url = _save_uploaded_media(request, provedor, cpf)
    if not file_url:
        file_url = (request.data.get('file_url') or '').strip()
    message_type = _guess_message_type(
        request.data.get('message_type') or request.data.get('media_type'),
        media,
        request.data.get('mime_type') or '',
    )
    if not content and not file_url:
        return Response({'error': 'Envie texto ou um arquivo.'}, status=400)

    preview = content or {
        'image': '📷 Imagem',
        'audio': '🎵 Áudio',
        'ptt': '🎤 Mensagem de voz',
        'video': '🎬 Vídeo',
        'document': '📎 Arquivo',
    }.get(message_type, 'Nova mensagem')

    agent_name = (request.data.get('agent_name') or request.data.get('sender_name') or '').strip()
    # Não usar nome do provedor no push — título = atendente ou o próprio texto
    if agent_name:
        push_title = agent_name[:80]
        push_body = preview[:180]
    else:
        push_title = preview[:80]
        push_body = ''

    try:
        push_result = send_push_notification_core(
            provedor.id,
            push_title,
            push_body,
            data={
                'type': 'support_chat',
                'screen': 'ai_chat',
                'cpf': cpf,
                'msg_type': message_type,
                'title': push_title,
                'body': push_body or preview[:180],
                'agent_name': agent_name,
            },
            source='support_chat',
            target_customer_ids=cpf,
        )
        logger.info(
            '[support-outbound] push provedor=%s cpf=%s result=%s',
            provedor.id,
            cpf,
            push_result,
        )
    except Exception:
        logger.exception('[support-outbound] Falha no push provedor=%s cpf=%s', provedor.id, cpf)
        push_result = {'status': 'error', 'reason': 'exception'}

    return Response({
        'success': True,
        'file_url': file_url or None,
        'message_type': message_type,
        'cpf': cpf,
        'push': push_result if isinstance(push_result, dict) else {'status': 'unknown'},
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def support_media_file(request, media_id):
    try:
        media = MobileSupportMedia.objects.get(id=media_id)
    except (MobileSupportMedia.DoesNotExist, ValueError, TypeError):
        raise Http404()
    if not media.file:
        raise Http404()
    try:
        fh = media.file.open('rb')
    except Exception:
        raise Http404()
    content_type = media.content_type or 'application/octet-stream'
    response = FileResponse(fh, content_type=content_type)
    if media.original_name:
        response['Content-Disposition'] = f'inline; filename="{smart_str(media.original_name)}"'
    return response
