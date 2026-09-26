"""
Aprendizado contínuo da IA — etapa 1: coleta de sinais dos atendimentos encerrados.

Lê só o banco local (as encerradas ficam até a rotina noturna) e grava AILearningAnalysis.
Sem LLM: identifica o que a IA resolveu sozinha, quando transferiu e quando o atendente assumiu.
"""
import logging
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)

PERIOD_DAYS = {'today': 0, '7d': 6, '30d': 29}
ANALYSIS_DELAY = timedelta(minutes=3)
AI_OUTCOMES = ('ai_resolved', 'ai_transferred', 'agent_took_over')
LEARNING_OUTCOMES = ('ai_transferred', 'agent_took_over')


def message_sender(msg):
    """customer | ai | chatbot | agent | system (avisos, resumos internos, disparos e o que não dá para afirmar)."""
    if msg.is_from_customer:
        return 'customer'
    attrs = msg.additional_attributes if isinstance(msg.additional_attributes, dict) else {}
    if attrs.get('system_message') or attrs.get('tipo') == 'resumo_suporte':
        return 'system'
    if attrs.get('from_ai') or attrs.get('is_ai_response'):
        return 'chatbot' if attrs.get('sender_type') == 'bot' else 'ai'
    if attrs.get('sent_by') or str(attrs.get('agent_name') or '').strip():
        return 'agent'
    content = msg.content or ''
    if content.lstrip().startswith('*') and 'disse:' in content[:120].lower():
        return 'agent'
    return 'system'


def _closed_at(conversation):
    from conversations.inbound_routing import conversation_ended_at

    value = conversation_ended_at(conversation)
    return parse_datetime(value) if isinstance(value, str) else value


def analyze_conversation(conversation):
    """Grava (ou atualiza) a análise do atendimento encerrado. Retorna AILearningAnalysis ou None."""
    from conversations.models import AILearningAnalysis

    inbox = conversation.inbox
    provedor_id = inbox.provedor_id if inbox else None
    if not provedor_id:
        return None

    counts = {'customer': 0, 'ai': 0, 'chatbot': 0, 'agent': 0, 'system': 0}
    ai_answered = False
    agent_after_ai = False
    messages = conversation.messages.order_by('created_at').only(
        'is_from_customer', 'additional_attributes', 'content', 'created_at',
    )
    for msg in messages:
        sender = message_sender(msg)
        counts[sender] += 1
        if sender == 'ai':
            ai_answered = True
        elif sender == 'agent' and ai_answered:
            agent_after_ai = True

    attrs = conversation.additional_attributes if isinstance(conversation.additional_attributes, dict) else {}
    transfer_reason = str(attrs.get('transfer_motivo') or '').strip()
    if counts['ai'] and transfer_reason:
        outcome = 'ai_transferred'
    elif counts['ai'] and agent_after_ai:
        outcome = 'agent_took_over'
    elif counts['ai']:
        outcome = 'ai_resolved'
    elif counts['agent']:
        outcome = 'human_only'
    elif counts['chatbot']:
        outcome = 'chatbot'
    else:
        outcome = 'no_reply'

    analysis, _ = AILearningAnalysis.objects.update_or_create(
        provedor_id=provedor_id,
        conversation_id=conversation.id,
        defaults={
            'contact_id': conversation.contact_id,
            'channel_type': (inbox.channel_type or '')[:30],
            'conversation_started_at': conversation.created_at,
            'conversation_closed_at': _closed_at(conversation),
            'customer_messages': counts['customer'],
            'ai_messages': counts['ai'],
            'chatbot_messages': counts['chatbot'],
            'agent_messages': counts['agent'],
            'outcome': outcome,
            'transfer_reason': transfer_reason if outcome == 'ai_transferred' else '',
            'learning_candidate': outcome in LEARNING_OUTCOMES,
        },
    )
    return analysis


def analyze_conversation_safe(conversation_id):
    """Análise antes da migração: nunca bloqueia o encerramento/migração."""
    from conversations.models import Conversation

    try:
        conversation = Conversation.objects.select_related('inbox').get(id=conversation_id)
        return analyze_conversation(conversation)
    except Conversation.DoesNotExist:
        return None
    except Exception:
        logger.exception('[AILearning] Falha ao analisar conversa %s', conversation_id)
        return None


def analyze_pending_closed(limit=200):
    """
    Analisa encerradas do banco local, sem análise, encerradas há pelo menos ANALYSIS_DELAY
    (tempo para CSAT ou reabertura). Retorna quantas analisou.
    """
    from django.db.models import DateTimeField
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast, Coalesce
    from conversations.inbound_routing import CLOSED_STATUSES
    from conversations.models import AILearningAnalysis, Conversation

    pending = (
        Conversation.objects.filter(status__in=CLOSED_STATUSES)
        .annotate(
            _closed_at=Coalesce(
                Cast(KeyTextTransform('closed_at', 'additional_attributes'), DateTimeField()),
                'updated_at',
            )
        )
        .filter(_closed_at__lte=timezone.now() - ANALYSIS_DELAY)
        .exclude(id__in=AILearningAnalysis.objects.values('conversation_id'))
        .select_related('inbox')
        .order_by('id')[:limit]
    )
    analyzed = 0
    for conversation in pending:
        try:
            if analyze_conversation(conversation):
                analyzed += 1
        except Exception:
            logger.exception('[AILearning] Falha ao analisar conversa %s', conversation.id)
    return analyzed


def learning_metrics(provedor_id, period='today'):
    """Números da aba Aprendizado da IA (período conta pela data de encerramento, fuso local)."""
    from conversations.models import AILearning, AILearningAnalysis, Contact
    from core.nightly_migration import local_midnight

    days = PERIOD_DAYS.get(period, 0)
    start = local_midnight() - timedelta(days=days)
    qs = AILearningAnalysis.objects.filter(provedor_id=provedor_id, conversation_closed_at__gte=start)

    by_outcome = {row['outcome']: row['n'] for row in qs.values('outcome').annotate(n=Count('id'))}
    total = sum(by_outcome.values())
    with_ai = sum(by_outcome.get(o, 0) for o in AI_OUTCOMES)
    ai_resolved = by_outcome.get('ai_resolved', 0)

    top_reasons = [
        {'reason': row['transfer_reason'], 'count': row['n']}
        for row in qs.filter(outcome='ai_transferred').exclude(transfer_reason='')
        .values('transfer_reason').annotate(n=Count('id')).order_by('-n')[:5]
    ]

    recent = list(qs.filter(learning_candidate=True).order_by('-conversation_closed_at')[:10])
    contacts = {
        c.id: c.name or c.phone
        for c in Contact.objects.filter(id__in=[a.contact_id for a in recent if a.contact_id]).only('id', 'name', 'phone')
    }

    return {
        'period': period if period in PERIOD_DAYS else 'today',
        'since': start.isoformat(),
        'analyzed': total,
        'with_ai': with_ai,
        'ai_resolved': ai_resolved,
        'ai_resolution_rate': round(ai_resolved * 100 / with_ai, 1) if with_ai else None,
        'ai_transfers': by_outcome.get('ai_transferred', 0),
        'agent_corrections': by_outcome.get('agent_took_over', 0),
        'by_outcome': by_outcome,
        'top_transfer_reasons': top_reasons,
        'recent_candidates': [
            {
                'conversation_id': a.conversation_id,
                'contact_name': contacts.get(a.contact_id) or 'Cliente',
                'channel_type': a.channel_type,
                'outcome': a.outcome,
                'transfer_reason': a.transfer_reason,
                'ai_messages': a.ai_messages,
                'agent_messages': a.agent_messages,
                'closed_at': a.conversation_closed_at.isoformat() if a.conversation_closed_at else None,
            }
            for a in recent
        ],
        # Base de aprendizados (não depende do período): aguardando revisão e ativos
        'suggested': AILearning.objects.filter(provedor_id=provedor_id, status='suggested').count(),
        'approved': AILearning.objects.filter(provedor_id=provedor_id, status='approved').count(),
    }
