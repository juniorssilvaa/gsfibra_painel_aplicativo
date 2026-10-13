"""Endpoints do Estúdio de Marketing (somente admin/superadmin do provedor)."""
from __future__ import annotations

import io

from django.http import HttpResponse
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from conversations.ai_learning_views import _can_manage, _resolve_provedor_id
from core.models import Provedor
from marketing import meta_ads
from marketing.assistant import ACTION_TTL, ToolError, execute_action, expire_stale_pending, start_turn
from marketing.meta_ads import MetaAdsError
from marketing.models import MarketingAsset, MarketingMessage, MarketingThread, MetaAdAction, MetaAdsConnection

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
        'width': asset.width,
        'height': asset.height,
        'original_name': asset.original_name,
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
        for a in MarketingAsset.objects.filter(provedor_id=thread.provedor_id, pk__in=ids).defer('image', 'base_image')
    }
    rows = list(thread.ad_actions.exclude(message=None).order_by('id'))
    latest_pending = max((a.id for a in rows if a.status == 'pending'), default=None)
    actions = {a.message_id: _action_dict(a, superseded=a.status == 'pending' and a.id != latest_pending) for a in rows}
    data = _thread_dict(thread)
    data['messages'] = [
        {
            'id': m.id,
            'role': m.role,
            'content': m.content,
            'status': m.status,
            'created_at': m.created_at.isoformat() if m.created_at else None,
            'assets': [assets[aid] for aid in (m.asset_ids or []) if aid in assets],
            'action': actions.get(m.id),
        }
        for m in messages
    ]
    return data


def _action_dict(action: MetaAdAction, superseded: bool = False):
    resumo = action.resumo or {}
    expired = action.status == 'pending' and action.created_at < timezone.now() - ACTION_TTL
    label = 'Substituída' if superseded else 'Expirada' if expired else action.get_status_display()
    return {
        'id': action.id,
        'kind': action.kind,
        'status': 'cancelled' if superseded or expired else action.status,
        'status_label': label,
        'nome': resumo.get('nome') or resumo.get('campanha') or '',
        'orcamento_diario': resumo.get('orcamento_diario') or (resumo.get('mudancas') or {}).get('orcamento_diario') or '',
        'campaign_id': action.campaign_id,
        'error': action.error if action.status == 'error' else '',
    }


def _action_reply(action: MetaAdAction, result) -> str:
    if not result.get('ok'):
        return f'Não consegui {"publicar" if action.kind == "create" else "aplicar"}: {result.get("erro") or "erro desconhecido"}'
    info = result.get('resultado') or {}
    if action.kind == 'create':
        return (
            f'Campanha publicada na Meta (ID {info.get("campanha_id")}). A Meta revisa o anúncio antes de começar a '
            'veicular, normalmente de alguns minutos a 24 horas. Você acompanha na aba Campanhas.'
        )
    changes = ', '.join(info.get('alterado') or []) or 'nenhuma mudança'
    return f'Alterações aplicadas na campanha (ID {info.get("campanha_id")}): {changes}.'


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
@parser_classes([JSONParser])
def thread_action(request, pk, action_id):
    """Botões do resumo: o clique do dono é a confirmação (ou o cancelamento) da ação preparada pela IA."""
    provedor_id, error = _context(request)
    if error:
        return error
    thread = _get_thread(provedor_id, pk)
    action = thread and thread.ad_actions.filter(pk=action_id).select_related('provedor').first()
    if not action:
        return Response({'error': 'Ação não encontrada nesta conversa.'}, status=status.HTTP_404_NOT_FOUND)
    decision = request.data.get('decision')
    if decision not in ('confirm', 'cancel'):
        return Response({'error': 'Decisão inválida.'}, status=status.HTTP_400_BAD_REQUEST)
    expire_stale_pending(thread)
    if thread.messages.filter(status='pending').exists():
        return Response({'error': 'Aguarde a IA terminar a resposta atual.'}, status=status.HTTP_409_CONFLICT)

    if decision == 'cancel':
        if not MetaAdAction.objects.filter(pk=action.pk, status='pending').update(status='cancelled', error='Cancelada pelo dono'):
            return Response({'error': f'Esta ação já está como "{action.get_status_display()}".'}, status=status.HTTP_409_CONFLICT)
        MarketingMessage.objects.create(thread=thread, role='user', content='Cancelar esse resumo.')
        MarketingMessage.objects.create(thread=thread, role='assistant', content='Ok, descartei esse resumo. Nada foi publicado.')
    else:
        try:
            result = execute_action(action)
        except ToolError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_409_CONFLICT)
        verb = 'Publicar na Meta.' if action.kind == 'create' else 'Aplicar as alterações na Meta.'
        MarketingMessage.objects.create(thread=thread, role='user', content=verb)
        MarketingMessage.objects.create(thread=thread, role='assistant', content=_action_reply(action, result))
    thread.save(update_fields=['updated_at'])
    return Response(_thread_detail(thread))


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
        jpeg = meta_ads.ad_image_jpeg(raw)
    except (UnidentifiedImageError, OSError, ValueError):
        return Response({'error': 'Arquivo não é uma imagem válida.'}, status=status.HTTP_400_BAD_REQUEST)
    width, height = Image.open(io.BytesIO(jpeg)).size
    thread = _get_thread(provedor_id, request.data.get('thread_id')) if request.data.get('thread_id') else None
    asset = MarketingAsset.objects.create(
        provedor_id=provedor_id,
        thread=thread,
        kind='reference',
        image=jpeg,
        mime_type='image/jpeg',
        width=width,
        height=height,
        original_name=str(upload.name or 'imagem')[:200],
        created_by=request.user,
    )
    return Response(_asset_dict(asset), status=status.HTTP_201_CREATED)


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
    response['Cache-Control'] = 'private, max-age=86400'
    return response


# ---------------------------------------------------------------- conexão Meta Ads

def _meta_status(conn):
    if not conn:
        return {'connected': False, 'ready': False}
    expired = bool(conn.token_expires_at and conn.token_expires_at <= timezone.now())
    return {
        'connected': bool(conn.access_token) and not expired,
        'expired': expired,
        'ready': conn.ready and not expired,
        'expires_at': conn.token_expires_at.isoformat() if conn.token_expires_at else None,
        'fb_user_name': conn.fb_user_name,
        'ad_account_id': conn.ad_account_id,
        'ad_account_name': conn.ad_account_name,
        'currency': conn.currency,
        'page_id': conn.page_id,
        'page_name': conn.page_name,
        'instagram_username': conn.instagram_username,
        'missing_scopes': [s for s in meta_ads.REQUIRED_SCOPES if s not in (conn.scopes or [])],
    }


def _meta_options(conn):
    return {
        'ad_accounts': meta_ads.list_ad_accounts(conn.access_token),
        'pages': meta_ads.list_pages(conn.access_token),
    }


@api_view(['GET', 'DELETE'])
@permission_classes([IsAuthenticated])
def meta_connection(request):
    provedor_id, error = _context(request)
    if error:
        return error
    if request.method == 'DELETE':
        MetaAdsConnection.objects.filter(provedor_id=provedor_id).delete()
        return Response(_meta_status(None))
    return Response(_meta_status(MetaAdsConnection.objects.filter(provedor_id=provedor_id).first()))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def meta_connect(request):
    provedor_id, error = _context(request)
    if error:
        return error
    try:
        info = meta_ads.exchange_token(str(request.data.get('access_token') or '').strip())
    except MetaAdsError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    conn, _ = MetaAdsConnection.objects.get_or_create(provedor_id=provedor_id, defaults={'access_token': info['access_token']})
    conn.access_token = info['access_token']
    conn.token_expires_at = info['expires_at']
    conn.scopes = info['scopes']
    conn.fb_user_id = info['user_id']
    conn.fb_user_name = info['user_name']
    conn.connected_by = request.user
    conn.save()
    data = _meta_status(conn)
    try:
        data.update(_meta_options(conn))
    except MetaAdsError as exc:
        data['options_error'] = str(exc)
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def meta_options(request):
    provedor_id, error = _context(request)
    if error:
        return error
    conn = MetaAdsConnection.objects.filter(provedor_id=provedor_id).first()
    if not conn or not conn.access_token:
        return Response({'error': 'Conecte o Facebook primeiro.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        return Response(_meta_options(conn))
    except MetaAdsError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


def _ready_connection(provedor_id):
    conn = MetaAdsConnection.objects.filter(provedor_id=provedor_id).first()
    status_data = _meta_status(conn)
    if not status_data['connected']:
        return None, Response({'error': 'Conecte o Facebook para ver suas campanhas.'}, status=status.HTTP_400_BAD_REQUEST)
    if not status_data['ready']:
        return None, Response({'error': 'Escolha a conta de anúncios e a Página.'}, status=status.HTTP_400_BAD_REQUEST)
    return conn, None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def meta_campaigns(request):
    provedor_id, error = _context(request)
    if error:
        return error
    conn, error = _ready_connection(provedor_id)
    if error:
        return error
    periodo = request.query_params.get('periodo') or '30d'
    if periodo not in meta_ads.PERIODOS:
        periodo = '30d'
    try:
        return Response(meta_ads.ads_overview(conn, periodo))
    except MetaAdsError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def meta_campaign_status(request, campaign_id):
    provedor_id, error = _context(request)
    if error:
        return error
    conn, error = _ready_connection(provedor_id)
    if error:
        return error
    new_status = request.data.get('status')
    if not campaign_id.isdigit() or new_status not in ('ACTIVE', 'PAUSED'):
        return Response({'error': 'Pedido inválido.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        meta_ads.set_campaign_status(conn, campaign_id, new_status)
    except MetaAdsError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({'ok': True, 'status': new_status})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([JSONParser])
def meta_config(request):
    provedor_id, error = _context(request)
    if error:
        return error
    conn = MetaAdsConnection.objects.filter(provedor_id=provedor_id).first()
    if not conn or not conn.access_token:
        return Response({'error': 'Conecte o Facebook primeiro.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        options = _meta_options(conn)
    except MetaAdsError as exc:
        return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    account = next((a for a in options['ad_accounts'] if a['id'] == request.data.get('ad_account_id')), None)
    page = next((p for p in options['pages'] if p['id'] == request.data.get('page_id')), None)
    if not account or not page:
        return Response({'error': 'Escolha uma conta de anúncios e uma Página da lista.'}, status=status.HTTP_400_BAD_REQUEST)
    conn.ad_account_id = account['id']
    conn.ad_account_name = account['name']
    conn.currency = account['currency']
    conn.page_id = page['id']
    conn.page_name = page['name']
    conn.instagram_user_id = page['instagram_user_id']
    conn.instagram_username = page['instagram_username']
    conn.save()
    return Response(_meta_status(conn))
