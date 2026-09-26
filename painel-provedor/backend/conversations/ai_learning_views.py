"""Endpoints da aba Aprendizado da IA (tela Desempenho da IA)."""
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from conversations.ai_learning import PERIOD_DAYS, learning_metrics

EDITABLE_STATUSES = ('suggested', 'approved', 'disabled', 'rejected')


def _resolve_provedor_id(request):
    data = request.data if isinstance(request.data, dict) else {}
    raw = request.query_params.get('provedor_id') or data.get('provedor_id')
    try:
        requested = int(raw or 0) or None
    except (TypeError, ValueError):
        requested = None
    user = request.user
    if getattr(user, 'user_type', None) == 'superadmin':
        return requested
    allowed = set(user.provedores_admin.values_list('id', flat=True))
    if getattr(user, 'provedor_id', None):
        allowed.add(user.provedor_id)
    if requested in allowed:
        return requested
    return next(iter(sorted(allowed)), None)


def _can_manage(user) -> bool:
    return getattr(user, 'user_type', None) in ('admin', 'superadmin')


def _serialize(item):
    return {
        'id': item.id,
        'situation': item.situation,
        'answer': item.answer,
        'keywords': item.keywords,
        'status': item.status,
        'source': item.source,
        'source_conversation_ids': item.source_conversation_ids or [],
        'review_reason': item.review_reason,
        'auto_approved': bool(item.source == 'llm' and item.approved_at and not item.approved_by_id),
        'times_used': item.times_used,
        'last_used_at': item.last_used_at.isoformat() if item.last_used_at else None,
        'approved_at': item.approved_at.isoformat() if item.approved_at else None,
        'created_at': item.created_at.isoformat() if item.created_at else None,
    }


def _clean_text(value, max_len):
    return str(value or '').strip()[:max_len]


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_learning_metrics(request):
    provedor_id = _resolve_provedor_id(request)
    if not provedor_id:
        return Response({'error': 'Provedor não encontrado'}, status=status.HTTP_400_BAD_REQUEST)
    period = request.query_params.get('period') or 'today'
    if period not in PERIOD_DAYS:
        period = 'today'
    return Response(learning_metrics(provedor_id, period))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def ai_learning_items(request):
    """GET lista (?status=suggested|approved|disabled|rejected); POST cadastra aprendizado manual (já aprovado)."""
    from ai.learnings import invalidate_cache
    from conversations.models import AILearning

    provedor_id = _resolve_provedor_id(request)
    if not provedor_id:
        return Response({'error': 'Provedor não encontrado'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'GET':
        qs = AILearning.objects.filter(provedor_id=provedor_id)
        wanted = request.query_params.get('status')
        if wanted in EDITABLE_STATUSES:
            qs = qs.filter(status=wanted)
        qs = qs.order_by('-times_used', '-id') if wanted == 'approved' else qs.order_by('-id')
        return Response({'results': [_serialize(i) for i in qs[:500]]})

    if not _can_manage(request.user):
        return Response({'error': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)
    situation = _clean_text(request.data.get('situation'), 300)
    answer = _clean_text(request.data.get('answer'), 2000)
    if not situation or not answer:
        return Response({'error': 'Informe a situação e como a IA deve agir.'}, status=status.HTTP_400_BAD_REQUEST)
    item = AILearning.objects.create(
        provedor_id=provedor_id,
        situation=situation,
        answer=answer,
        keywords=_clean_text(request.data.get('keywords'), 500),
        status='approved',
        source='manual',
        approved_at=timezone.now(),
        approved_by=request.user,
    )
    invalidate_cache(provedor_id)
    return Response(_serialize(item), status=status.HTTP_201_CREATED)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def ai_learning_item_detail(request, pk):
    """PATCH edita texto/status (aprovar, rejeitar, desativar, reativar); DELETE exclui."""
    from ai.learnings import invalidate_cache
    from conversations.models import AILearning

    if not _can_manage(request.user):
        return Response({'error': 'Sem permissão'}, status=status.HTTP_403_FORBIDDEN)
    provedor_id = _resolve_provedor_id(request)
    item = AILearning.objects.filter(pk=pk, provedor_id=provedor_id).first()
    if not item:
        return Response({'error': 'Aprendizado não encontrado'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'DELETE':
        item.delete()
        invalidate_cache(provedor_id)
        return Response(status=status.HTTP_204_NO_CONTENT)

    fields = []
    for field, max_len in (('situation', 300), ('answer', 2000), ('keywords', 500)):
        if field in request.data:
            value = _clean_text(request.data.get(field), max_len)
            if field != 'keywords' and not value:
                return Response({'error': 'Situação e como agir não podem ficar vazios.'}, status=status.HTTP_400_BAD_REQUEST)
            setattr(item, field, value)
            fields.append(field)
    new_status = request.data.get('status')
    if new_status is not None:
        if new_status not in EDITABLE_STATUSES:
            return Response({'error': 'Status inválido'}, status=status.HTTP_400_BAD_REQUEST)
        if new_status == 'approved' and item.status != 'approved':
            item.approved_at = timezone.now()
            item.approved_by = request.user
            fields += ['approved_at', 'approved_by']
        item.status = new_status
        fields.append('status')
    if fields:
        item.save(update_fields=fields + ['updated_at'])
        invalidate_cache(provedor_id)
    return Response(_serialize(item))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_learning_export(request):
    """Exporta os aprendizados aprovados em Markdown (rag.md do provedor)."""
    from conversations.models import AILearning
    from core.models import Provedor

    provedor_id = _resolve_provedor_id(request)
    if not provedor_id:
        return Response({'error': 'Provedor não encontrado'}, status=status.HTTP_400_BAD_REQUEST)
    provedor = Provedor.objects.filter(pk=provedor_id).only('nome').first()
    items = AILearning.objects.filter(provedor_id=provedor_id, status='approved').order_by('-times_used', '-id')
    lines = [
        f"# Aprendizados da IA — {getattr(provedor, 'nome', '') or f'Provedor {provedor_id}'}",
        '',
        f"Exportado em {timezone.localtime().strftime('%d/%m/%Y %H:%M')} · {items.count()} aprendizado(s) ativo(s)",
        '',
    ]
    for index, item in enumerate(items, start=1):
        lines += [f'## {index}. {item.situation}', '', item.answer, '']
        if item.keywords:
            lines += [f'**Palavras-chave:** {item.keywords}', '']
    response = HttpResponse('\n'.join(lines), content_type='text/markdown; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="rag.md"'
    return response
