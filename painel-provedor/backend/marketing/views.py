"""Endpoints do Estúdio de Marketing (somente admin/superadmin do provedor)."""
from __future__ import annotations

import io

from django.http import HttpResponse
from PIL import Image, UnidentifiedImageError
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from conversations.ai_learning_views import _can_manage, _resolve_provedor_id
from core.models import Provedor
from marketing.assistant import expire_stale_pending, start_turn
from marketing.image_engine import (
    IMAGE_PROVIDERS,
    agent_key_supports_images,
    image_engine_status,
    reference_png,
    validate_api_key,
)
from marketing.models import MarketingAsset, MarketingMessage, MarketingThread

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_MESSAGE_CHARS = 4000
SUPPORT_ONLY_MSG = 'O Estúdio de Marketing está disponível apenas no painel em modo suporte.'


def _context(request):
    """(provedor_id, erro) — o Estúdio é restrito a quem administra o provedor em modo suporte."""
    if not _can_manage(request.user):
        return None, Response({'error': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)
    provedor_id = _resolve_provedor_id(request)
    if not provedor_id:
        return None, Response({'error': 'Provedor não encontrado'}, status=status.HTTP_400_BAD_REQUEST)
    mode = Provedor.objects.filter(pk=provedor_id).values_list('agent_mode', flat=True).first()
    if (mode or 'isp').strip().lower() != 'support':
        return None, Response({'error': SUPPORT_ONLY_MSG, 'code': 'support_only'}, status=status.HTTP_403_FORBIDDEN)
    return provedor_id, None


def _asset_dict(asset: MarketingAsset):
    return {
        'id': asset.id,
        'kind': asset.kind,
        'formato': asset.formato,
        'modo_texto': asset.modo_texto,
        'width': asset.width,
        'height': asset.height,
        'approved': asset.approved,
        'original_name': asset.original_name,
        'plano_nome': asset.plano.nome if asset.plano_id and asset.plano else None,
        'parent_id': asset.parent_id,
        'created_at': asset.created_at.isoformat() if asset.created_at else None,
    }


def _thread_dict(thread: MarketingThread):
    return {
        'id': thread.id,
        'title': thread.title,
        'created_at': thread.created_at.isoformat() if thread.created_at else None,
        'updated_at': thread.updated_at.isoformat() if thread.updated_at else None,
    }


def _thread_detail(thread: MarketingThread):
    expire_stale_pending(thread)
    messages = list(thread.messages.order_by('id'))
    ids = {aid for m in messages for aid in (m.asset_ids or [])}
    assets = {
        a.id: _asset_dict(a)
        for a in MarketingAsset.objects.filter(provedor_id=thread.provedor_id, pk__in=ids)
        .select_related('plano').defer('image', 'base_image')
    }
    data = _thread_dict(thread)
    data['messages'] = [
        {
            'id': m.id,
            'role': m.role,
            'content': m.content,
            'status': m.status,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'assets': [assets[aid] for aid in (m.asset_ids or []) if aid in assets],
        }
        for m in messages
    ]
    return data


def _get_thread(provedor_id, pk):
    return MarketingThread.objects.filter(provedor_id=provedor_id, pk=pk).first()


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def threads(request):
    provedor_id, error = _context(request)
    if error:
        return error
    if request.method == 'GET':
        qs = MarketingThread.objects.filter(provedor_id=provedor_id).order_by('-updated_at')[:100]
        return Response({'results': [_thread_dict(t) for t in qs]})
    title = str(request.data.get('title') or '').strip()[:200] or 'Nova conversa'
    thread = MarketingThread.objects.create(provedor_id=provedor_id, title=title, created_by=request.user)
    return Response(_thread_detail(thread), status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def thread_detail(request, pk):
    provedor_id, error = _context(request)
    if error:
        return error
    thread = _get_thread(provedor_id, pk)
    if not thread:
        return Response({'error': 'Conversa não encontrada'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        thread.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if request.method == 'PATCH':
        title = str(request.data.get('title') or '').strip()[:200]
        if title:
            thread.title = title
            thread.save(update_fields=['title', 'updated_at'])
    return Response(_thread_detail(thread))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def thread_messages(request, pk):
    provedor_id, error = _context(request)
    if error:
        return error
    thread = _get_thread(provedor_id, pk)
    if not thread:
        return Response({'error': 'Conversa não encontrada'}, status=status.HTTP_404_NOT_FOUND)
    expire_stale_pending(thread)
    if thread.messages.filter(status='pending').exists():
        return Response({'error': 'Aguarde a IA terminar a resposta atual.'}, status=status.HTTP_409_CONFLICT)

    content = str(request.data.get('content') or '').strip()[:MAX_MESSAGE_CHARS]
    raw_ids = request.data.get('reference_ids') or []
    ref_ids = list(
        MarketingAsset.objects.filter(provedor_id=provedor_id, pk__in=[i for i in raw_ids if str(i).isdigit()])
        .values_list('id', flat=True)
    ) if isinstance(raw_ids, list) else []
    if not content and not ref_ids:
        return Response({'error': 'Escreva uma mensagem ou anexe uma imagem.'}, status=status.HTTP_400_BAD_REQUEST)

    MarketingMessage.objects.create(thread=thread, role='user', content=content, asset_ids=ref_ids)
    pending = MarketingMessage.objects.create(thread=thread, role='assistant', status='pending')
    if thread.title == 'Nova conversa' and content:
        thread.title = content[:60]
    thread.save(update_fields=['title', 'updated_at'])
    start_turn(pending.id)
    return Response(_thread_detail(thread), status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_reference(request):
    provedor_id, error = _context(request)
    if error:
        return error
    upload = request.FILES.get('file')
    if not upload:
        return Response({'error': 'Envie uma imagem.'}, status=status.HTTP_400_BAD_REQUEST)
    if upload.size > MAX_UPLOAD_BYTES:
        return Response({'error': 'Imagem maior que 8 MB.'}, status=status.HTTP_400_BAD_REQUEST)
    raw = upload.read()
    try:
        Image.open(io.BytesIO(raw)).verify()
        png = reference_png(raw, max_side=2048)
    except (UnidentifiedImageError, OSError, ValueError):
        return Response({'error': 'Arquivo não é uma imagem válida.'}, status=status.HTTP_400_BAD_REQUEST)
    width, height = Image.open(io.BytesIO(png)).size
    thread = _get_thread(provedor_id, request.data.get('thread_id')) if request.data.get('thread_id') else None
    asset = MarketingAsset.objects.create(
        provedor_id=provedor_id,
        thread=thread,
        kind='reference',
        image=png,
        mime_type='image/png',
        width=width,
        height=height,
        original_name=str(upload.name or 'imagem')[:200],
        created_by=request.user,
    )
    return Response(_asset_dict(asset), status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def assets(request):
    provedor_id, error = _context(request)
    if error:
        return error
    qs = MarketingAsset.objects.filter(provedor_id=provedor_id, kind='creative')
    if request.query_params.get('approved') in ('1', 'true'):
        qs = qs.filter(approved=True)
    qs = qs.select_related('plano').defer('image', 'base_image').order_by('-id')[:200]
    return Response({'results': [_asset_dict(a) for a in qs]})


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def asset_detail(request, pk):
    provedor_id, error = _context(request)
    if error:
        return error
    asset = MarketingAsset.objects.filter(provedor_id=provedor_id, pk=pk).first()
    if not asset:
        return Response({'error': 'Imagem não encontrada'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'DELETE':
        asset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    if 'approved' in request.data:
        asset.approved = bool(request.data.get('approved'))
        asset.save(update_fields=['approved'])
    return Response(_asset_dict(asset))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def asset_image(request, pk):
    provedor_id, error = _context(request)
    if error:
        return error
    asset = MarketingAsset.objects.filter(provedor_id=provedor_id, pk=pk).only('image', 'mime_type', 'kind').first()
    if not asset:
        return Response({'error': 'Imagem não encontrada'}, status=status.HTTP_404_NOT_FOUND)
    response = HttpResponse(bytes(asset.image), content_type=asset.mime_type or 'image/jpeg')
    if request.query_params.get('download') in ('1', 'true'):
        ext = 'png' if asset.mime_type == 'image/png' else 'jpg'
        response['Content-Disposition'] = f'attachment; filename="arte-{asset.id}.{ext}"'
    response['Cache-Control'] = 'private, max-age=86400'
    return response


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def engine_settings(request):
    provedor_id, error = _context(request)
    if error:
        return error
    provedor = Provedor.objects.filter(pk=provedor_id).first()
    if not provedor:
        return Response({'error': 'Provedor não encontrado'}, status=status.HTTP_404_NOT_FOUND)
    if request.method == 'POST':
        image_provider = str(request.data.get('image_provider') or '').strip().lower()
        image_api_key = str(request.data.get('image_api_key') or '').strip()
        ext = dict(provedor.integracoes_externas or {})
        if request.data.get('remove'):
            ext.pop('image_provider', None)
            ext.pop('image_api_key', None)
        elif agent_key_supports_images(provedor):
            return Response(
                {'error': 'O Estúdio usa a mesma chave do Agente de IA (Integrações). Para trocar, altere a chave lá.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        else:
            if image_provider not in IMAGE_PROVIDERS:
                return Response({'error': 'Escolha OpenAI ou Gemini.'}, status=status.HTTP_400_BAD_REQUEST)
            key_to_check = image_api_key or ext.get('image_api_key') or ''
            if not key_to_check:
                return Response({'error': 'Informe a chave da API.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                validate_api_key(image_provider, key_to_check)
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            ext['image_provider'] = image_provider
            if image_api_key:
                ext['image_api_key'] = image_api_key
        provedor.integracoes_externas = ext
        provedor.save(update_fields=['integracoes_externas'])
    return Response(image_engine_status(provedor))
