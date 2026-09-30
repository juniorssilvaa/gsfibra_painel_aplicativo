"""
Contagem de encerramentos por automação (chatbot/IA) e por atendente humano.
Conta eventos de encerramento (AuditLog), não o estado atual da conversa:
a mesma conversa reaberta e encerrada de novo conta outra vez.
"""
import logging

from conversations.closure_audit import AUTOMATION_CLOSE_ACTIONS, MANUAL_CLOSE_ACTIONS

logger = logging.getLogger(__name__)


def _count_closure_events(provedor, actions) -> int:
    from core.models import AuditLog

    try:
        return AuditLog.objects.filter(provedor=provedor, action__in=actions).count()
    except Exception as e:
        logger.warning(
            "[DashboardStats] Erro ao contar encerramentos %s provedor %s: %s",
            actions,
            provedor.id,
            e,
        )
        return 0


def get_resolution_breakdown(provedor) -> dict:
    automacao = _count_closure_events(provedor, AUTOMATION_CLOSE_ACTIONS)
    manual = _count_closure_events(provedor, MANUAL_CLOSE_ACTIONS)

    return {
        'resolvidas_automacao_ia': automacao,
        'resolvidas_automacao_local': automacao,
        'resolvidas_automacao_supabase': 0,
        'resolvidas_encerrado_manual': manual,
        'resolvidas_manual_local': manual,
        'resolvidas_manual_supabase': 0,
        'resolvidas_demais_encerramentos': manual,
    }
