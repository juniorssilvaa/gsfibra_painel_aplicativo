"""
Contagem de conversas encerradas por automação (chatbot/IA) e por atendente humano.
Alinha dashboard com todos os fluxos: nó close do chatbot, IA encerrar_atendimento, finalize_closing, etc.
"""
import logging
from django.db.models import Q

from conversations.models import Conversation

logger = logging.getLogger(__name__)

CLOSED_STATUSES = ['closed', 'encerrada', 'resolved', 'finalizada']


def _automacao_trace_q() -> Q:
    """Marcadores gravados ao encerrar pelo chatbot/IA."""
    return (
        Q(additional_attributes__resolucao_automacao=True)
        | Q(additional_attributes__encerrado_por='ai')
        | Q(additional_attributes__closure_source__startswith='chatbot')
        | Q(additional_attributes__closure_source__startswith='ia_')
    )


def _status_encerrada_q() -> Q:
    """Fechada ou em closing com rastro de automação (aguardando finalize_closing)."""
    return Q(status__in=CLOSED_STATUSES) | Q(
        status='closing',
        additional_attributes__resolucao_automacao=True,
    )


def count_automation_resolutions_local(provedor) -> int:
    provedor_filter = Q(inbox__provedor=provedor)
    try:
        return (
            Conversation.objects.filter(provedor_filter)
            .filter(_status_encerrada_q())
            .filter(_automacao_trace_q())
            .count()
        )
    except Exception as e:
        logger.warning(
            "[DashboardStats] Erro ao contar automação (local) provedor %s: %s",
            provedor.id,
            e,
        )
        return 0


def count_manual_resolutions_local(provedor) -> int:
    provedor_filter = Q(inbox__provedor=provedor)
    try:
        return (
            Conversation.objects.filter(provedor_filter)
            .filter(status__in=CLOSED_STATUSES)
            .filter(Q(additional_attributes__encerrado_por='agent'))
            .count()
        )
    except Exception as e:
        logger.warning(
            "[DashboardStats] Erro ao contar manual (local) provedor %s: %s",
            provedor.id,
            e,
        )
        return 0


def _count_supabase_conversations(provedor_id: int, or_filter: str) -> int:
    import requests
    from django.conf import settings

    if not getattr(settings, 'SUPABASE_ENABLED', True):
        return 0

    timeout = getattr(settings, 'SUPABASE_REQUEST_TIMEOUT', 8)
    url = f"{settings.SUPABASE_URL}/rest/v1/conversations"
    headers = {
        'apikey': settings.SUPABASE_ANON_KEY,
        'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
        'Content-Type': 'application/json',
        'Prefer': 'count=exact',
    }
    params = {
        'provedor_id': f'eq.{provedor_id}',
        'status': 'eq.closed',
        'or': or_filter,
        'select': 'id,provedor_id',
    }
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    if resp.status_code != 200:
        return 0

    data = resp.json()
    if isinstance(data, list):
        return sum(1 for item in data if item.get('provedor_id') == provedor_id)

    content_range = resp.headers.get('Content-Range', '')
    if content_range and '/' in content_range:
        try:
            return int(content_range.split('/')[-1])
        except (ValueError, IndexError):
            pass
    return 0


def count_automation_resolutions_supabase(provedor) -> int:
    # resolucao_automacao, encerrado_por=ai, ou closure_source do chatbot/IA
    or_filter = (
        '(additional_attributes->>encerrado_por.eq.ai,'
        'additional_attributes->>resolucao_automacao.eq.true,'
        'additional_attributes->>closure_source.like.chatbot%,'
        'additional_attributes->>closure_source.like.ia_%)'
    )
    try:
        count = _count_supabase_conversations(provedor.id, or_filter)
        if count:
            return count
    except Exception as e:
        logger.warning(
            "[DashboardStats] Filtro amplo Supabase falhou provedor %s: %s",
            provedor.id,
            e,
        )
    try:
        return _count_supabase_conversations(
            provedor.id,
            '(additional_attributes->>encerrado_por.eq.ai,additional_attributes->>resolucao_automacao.eq.true)',
        )
    except Exception as e:
        logger.warning(
            "[DashboardStats] Erro ao contar automação (Supabase) provedor %s: %s",
            provedor.id,
            e,
        )
        return 0


def count_manual_resolutions_supabase(provedor) -> int:
    try:
        return _count_supabase_conversations(
            provedor.id,
            '(additional_attributes->>encerrado_por.eq.agent)',
        )
    except Exception as e:
        logger.warning(
            "[DashboardStats] Erro ao contar manual (Supabase) provedor %s: %s",
            provedor.id,
            e,
        )
        return 0


def get_resolution_breakdown(provedor) -> dict:
    auto_local = count_automation_resolutions_local(provedor)
    auto_supabase = count_automation_resolutions_supabase(provedor)
    manual_local = count_manual_resolutions_local(provedor)
    manual_supabase = count_manual_resolutions_supabase(provedor)

    return {
        'resolvidas_automacao_ia': auto_local + auto_supabase,
        'resolvidas_automacao_local': auto_local,
        'resolvidas_automacao_supabase': auto_supabase,
        'resolvidas_encerrado_manual': manual_local + manual_supabase,
        'resolvidas_manual_local': manual_local,
        'resolvidas_manual_supabase': manual_supabase,
        'resolvidas_demais_encerramentos': manual_local + manual_supabase,
    }
