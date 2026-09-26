"""
Base de aprendizados da IA por provedor (RAG leve, fora do prompt base).

- Busca: a cada mensagem, compara o texto do cliente com os aprendizados APROVADOS do provedor
  (palavras-chave e situação) e devolve só os mais relevantes; o prompt não cresce com a base.
- Sugestões: o LLM do próprio provedor lê atendimentos em que a IA precisou de ajuda humana e
  propõe aprendizados gerais. Os de baixo risco (procedimento, orientação) são aprovados
  automaticamente; os que envolvem valores, descontos, prazos, promessas ou dados de pagamento
  aguardam o admin na tela Desempenho da IA.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata

from django.conf import settings
from django.db.models import F
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_INJECTED = 4
MIN_SCORE = 2
MAX_LOADED = 1000
CACHE_TTL_SECONDS = 30
TRANSCRIPT_MAX_MESSAGES = 40
TRANSCRIPT_MAX_CHARS = 500

_STOPWORDS = {
    'que', 'para', 'com', 'uma', 'uns', 'umas', 'por', 'pra', 'pro', 'dos', 'das', 'nos', 'nas', 'num', 'numa',
    'mais', 'mas', 'como', 'quando', 'onde', 'qual', 'quais', 'meu', 'minha', 'meus', 'minhas', 'seu', 'sua',
    'voce', 'voces', 'ele', 'ela', 'eles', 'elas', 'isso', 'isto', 'esse', 'essa', 'este', 'esta', 'aqui',
    'ali', 'tem', 'ter', 'tenho', 'tinha', 'estou', 'esta', 'estao', 'foi', 'ser', 'sao', 'sim', 'nao',
    'bom', 'boa', 'dia', 'tarde', 'noite', 'ola', 'oi', 'obrigado', 'obrigada', 'favor', 'gostaria',
    'queria', 'quero', 'preciso', 'pode', 'posso', 'cliente', 'sobre', 'entao', 'tambem', 'ainda', 'ja',
}

_RISK_RULES = [
    ('valores', re.compile(r'r\$|\breais\b|\bvalor|\bpreco|\bcusto|\btaxa|\bmensalidade|\bmulta|\bjuros')),
    ('descontos ou isenções', re.compile(r'\bdesconto|\babatimento|\bgratis|\bgratuit|\bisen|\bcortesia|\bbonus'
                                         r'|\bestorn|\breembols')),
    ('prazos', re.compile(r'\bprazo|\d+\s*(?:h|hs|hr|hrs|horas?|min|minutos?|dias?|semanas?|mes|meses)\b'
                          r'|\bem ate\b|\bimediat|\bhoje mesmo|\bamanha')),
    ('promessas ou garantias', re.compile(r'\bpromet|\bgarant|\bcompromet|\bassegur|\bsem custo')),
    ('dados de pagamento ou números', re.compile(r'\bpix\b|\bchave\b|\bconta bancaria|\bagencia\b|\d{4,}')),
]

_cache: dict = {}


def _normalize(text) -> str:
    text = unicodedata.normalize('NFKD', str(text or '').lower())
    return ''.join(c for c in text if not unicodedata.combining(c))


def _tokens(text) -> set:
    """Palavras normalizadas (sem acento, minúsculas, radical de 5 letras) para comparação."""
    return {w[:5] for w in re.findall(r'[a-z0-9]{3,}', _normalize(text)) if w not in _STOPWORDS}


def risk_reasons(situation, answer) -> list:
    """Temas sensíveis encontrados no texto; qualquer um exige revisão do admin."""
    text = _normalize(f'{situation}\n{answer}')
    return [label for label, pattern in _RISK_RULES if pattern.search(text)]


def review_reason_for(item) -> str:
    """Motivo para a sugestão aguardar o admin ('' = pode ser aprovada automaticamente)."""
    reasons = risk_reasons(item['situation'], item['answer'])
    if reasons:
        return 'Envolve ' + ', '.join(reasons)
    if item.get('risk') != 'baixo':
        return (item.get('risk_reason') or 'A IA marcou como sensível')[:200]
    return ''


def invalidate_cache(provedor_id) -> None:
    _cache.pop(provedor_id, None)


def _approved_items(provedor_id):
    from conversations.models import AILearning

    now = time.monotonic()
    hit = _cache.get(provedor_id)
    if hit and hit[0] > now:
        return hit[1]
    rows = (
        AILearning.objects.filter(provedor_id=provedor_id, status='approved')
        .order_by('-times_used', '-id')
        .values('id', 'situation', 'answer', 'keywords')[:MAX_LOADED]
    )
    items = [
        {**row, 'kw_tokens': _tokens(row['keywords']), 'sit_tokens': _tokens(row['situation'])}
        for row in rows
    ]
    _cache[provedor_id] = (now + CACHE_TTL_SECONDS, items)
    return items


def relevant_learnings(provedor_id, text, limit=MAX_INJECTED):
    query = _tokens(text)
    if not query:
        return []
    scored = []
    for item in _approved_items(provedor_id):
        score = 2 * len(query & item['kw_tokens']) + len(query & item['sit_tokens'])
        if score >= MIN_SCORE:
            scored.append((score, item))
    scored.sort(key=lambda pair: -pair[0])
    return [item for _, item in scored[:limit]]


def learnings_system_message(provedor_id, text):
    """Mensagem de sistema com os aprendizados relevantes (None se nenhum casar)."""
    from conversations.models import AILearning

    items = relevant_learnings(provedor_id, text)
    if not items:
        return None
    AILearning.objects.filter(id__in=[i['id'] for i in items]).update(
        times_used=F('times_used') + 1, last_used_at=timezone.now(),
    )
    lines = [
        'Aprendizados aprovados por este provedor que podem se aplicar a esta mensagem. '
        'Use-os se forem pertinentes; dados retornados pelas tools e as regras do provedor têm prioridade.'
    ]
    for item in items:
        lines.append(f"- Situação: {item['situation']}\n  Como agir: {item['answer']}")
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Sugestões geradas pelo LLM
# ---------------------------------------------------------------------------

_SUGGESTION_PROMPT = """Você analisa atendimentos encerrados de um provedor para melhorar o assistente virtual (IA) dele.
Neste atendimento a IA precisou de ajuda humana. Extraia no máximo 2 aprendizados GERAIS e reutilizáveis que fariam a IA resolver casos parecidos sozinha no futuro.

Regras:
- Nada de dados pessoais ou específicos deste cliente (nome, CPF, telefone, endereço, contrato, valores de fatura, protocolo).
- Registre só o que o atendente humano ensinou ou esclareceu e que valha para outros clientes (procedimento, política, informação do provedor).
- Se o humano apenas executou uma ação que a IA não pode fazer, ou se nada for reaproveitável, retorne a lista vazia.
- Não repita aprendizados que já existem (lista enviada).
- "situacao": quando aplicar (ex.: "Cliente pergunta se pode pagar a fatura em lotérica"), até 200 caracteres.
- "como_agir": instrução direta para a IA, em português, até 600 caracteres.
- "palavras_chave": 3 a 8 palavras que o cliente usaria ao perguntar.
- "risco": "baixo" se for só procedimento, orientação ou informação geral; "alto" se envolver valores, descontos, isenções, prazos, promessas, garantias, exceções à política ou qualquer compromisso do provedor.
- "motivo_risco": se o risco for alto, o motivo em até 80 caracteres.

Responda SOMENTE com JSON: {"aprendizados": [{"situacao": "...", "como_agir": "...", "palavras_chave": ["..."], "risco": "baixo", "motivo_risco": ""}]}"""

_SENDER_LABELS = {'customer': 'Cliente', 'ai': 'IA', 'chatbot': 'Chatbot', 'agent': 'Atendente'}


def _transcript(conversation) -> str:
    from conversations.ai_learning import message_sender

    lines = []
    messages = list(conversation.messages.order_by('-created_at')[:TRANSCRIPT_MAX_MESSAGES])
    for msg in reversed(messages):
        label = _SENDER_LABELS.get(message_sender(msg))
        content = (msg.content or '').strip()
        if not label or not content:
            continue
        lines.append(f'{label}: {content[:TRANSCRIPT_MAX_CHARS]}')
    return '\n'.join(lines)


def _parse_suggestions(raw) -> list:
    text = (raw or '').strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return []
    result = []
    for item in (data.get('aprendizados') or [])[:2]:
        if not isinstance(item, dict):
            continue
        situation = str(item.get('situacao') or '').strip()[:300]
        answer = str(item.get('como_agir') or '').strip()[:2000]
        keywords = item.get('palavras_chave') or []
        if isinstance(keywords, str):
            keywords = [keywords]
        keywords = ', '.join(str(k).strip() for k in keywords if str(k).strip())[:500]
        if situation and answer:
            result.append({
                'situation': situation,
                'answer': answer,
                'keywords': keywords,
                'risk': _normalize(item.get('risco')).strip(),
                'risk_reason': str(item.get('motivo_risco') or '').strip(),
            })
    return result


def _auto_approve_enabled() -> bool:
    return bool(getattr(settings, 'AI_LEARNING_AUTO_APPROVE_SAFE', True))


def _daily_limit() -> int:
    return int(getattr(settings, 'AI_LEARNING_DAILY_LIMIT', 30) or 0)


def _attempts_today(provedor_id) -> int:
    from conversations.models import AILearningAnalysis
    from core.nightly_migration import local_midnight

    return AILearningAnalysis.objects.filter(
        provedor_id=provedor_id, suggestion_attempted_at__gte=local_midnight(),
    ).count()


def generate_suggestions(analysis) -> str:
    """Gera sugestões para um atendimento candidato. Retorna o novo suggestion_status."""
    from ai.providers import get_provider_client
    from conversations.models import AILearning, Conversation

    conversation = (
        Conversation.objects.select_related('inbox__provedor').filter(id=analysis.conversation_id).first()
    )
    status = 'skipped'
    created = 0
    auto_approved = 0
    try:
        provedor = conversation.inbox.provedor if conversation and conversation.inbox else None
        provider = get_provider_client(provedor) if provedor else None
        transcript = _transcript(conversation) if conversation else ''
        if not provider or not provider.available:
            status = 'failed'
        elif transcript:
            existing = list(
                AILearning.objects.filter(provedor_id=analysis.provedor_id, status__in=['approved', 'suggested'])
                .order_by('-id').values_list('situation', flat=True)[:60]
            )
            context = [
                'Resultado: ' + ('a IA transferiu para humano' if analysis.outcome == 'ai_transferred'
                                 else 'o atendente assumiu a conversa da IA'),
            ]
            if analysis.transfer_reason:
                context.append(f'Motivo da transferência: {analysis.transfer_reason}')
            context.append('Aprendizados já existentes:\n' + ('\n'.join(f'- {s}' for s in existing) or '(nenhum)'))
            context.append(f'Atendimento:\n{transcript}')
            response = provider.client().chat.completions.create(
                model=provider.model,
                messages=[
                    {'role': 'system', 'content': _SUGGESTION_PROMPT},
                    {'role': 'user', 'content': '\n\n'.join(context)},
                ],
                temperature=0.2,
                max_tokens=700,
                timeout=30,
            )
            suggestions = _parse_suggestions(response.choices[0].message.content)
            auto_approve = _auto_approve_enabled()
            for item in suggestions:
                reason = review_reason_for(item)
                approved = auto_approve and not reason
                AILearning.objects.create(
                    provedor_id=analysis.provedor_id,
                    source='llm',
                    status='approved' if approved else 'suggested',
                    approved_at=timezone.now() if approved else None,
                    review_reason=reason,
                    source_conversation_ids=[analysis.conversation_id],
                    situation=item['situation'],
                    answer=item['answer'],
                    keywords=item['keywords'],
                )
                created += 1
                auto_approved += int(approved)
            if auto_approved:
                invalidate_cache(analysis.provedor_id)
            status = 'done' if created else 'skipped'
    except Exception:
        logger.exception('[AILearning] Falha ao gerar sugestões conv=%s', analysis.conversation_id)
        status = 'failed'

    analysis.suggestion_status = status
    analysis.suggestion_attempted_at = timezone.now()
    analysis.save(update_fields=['suggestion_status', 'suggestion_attempted_at'])
    if created:
        logger.info(
            '[AILearning] %s sugestão(ões) criada(s), %s aprovada(s) automaticamente conv=%s',
            created, auto_approved, analysis.conversation_id,
        )
    return status


def _can_suggest(analysis) -> bool:
    if not getattr(settings, 'AI_LEARNING_SUGGESTIONS_ENABLED', True):
        return False
    return _attempts_today(analysis.provedor_id) < _daily_limit()


def process_pending_suggestions(limit=10) -> int:
    """Processa candidatos pendentes (respeitando o limite diário por provedor). Retorna quantos tentou."""
    from conversations.models import AILearningAnalysis

    attempted = 0
    pending = AILearningAnalysis.objects.filter(learning_candidate=True, suggestion_status='pending').order_by('id')
    for analysis in pending[:limit]:
        if not _can_suggest(analysis):
            continue
        generate_suggestions(analysis)
        attempted += 1
    return attempted


_suggestions_lock = threading.Lock()
_suggestions_running = False


def _suggestions_thread_main() -> None:
    global _suggestions_running
    from django.db import close_old_connections

    close_old_connections()
    try:
        attempted = process_pending_suggestions()
        if attempted:
            logger.info('[AILearning] %s atendimento(s) enviados para sugestão', attempted)
    except Exception:
        logger.exception('[AILearning] erro no processamento de sugestões')
    finally:
        close_old_connections()
        with _suggestions_lock:
            _suggestions_running = False


def start_pending_suggestions() -> bool:
    """Dispara o processamento em thread (chamadas ao LLM não seguram o loop periódico)."""
    global _suggestions_running
    from conversations.models import AILearningAnalysis

    if not getattr(settings, 'AI_LEARNING_SUGGESTIONS_ENABLED', True):
        return False
    with _suggestions_lock:
        if _suggestions_running:
            return False
        if not AILearningAnalysis.objects.filter(learning_candidate=True, suggestion_status='pending').exists():
            return False
        _suggestions_running = True
    threading.Thread(target=_suggestions_thread_main, name='niochat-ai-learning', daemon=True).start()
    return True


def suggest_before_migration_safe(conversation_id) -> None:
    """Rotina noturna: gera a sugestão pendente antes de a conversa sair do banco local."""
    from conversations.models import AILearningAnalysis

    try:
        analysis = AILearningAnalysis.objects.filter(
            conversation_id=conversation_id, learning_candidate=True, suggestion_status='pending',
        ).first()
        if analysis and _can_suggest(analysis):
            generate_suggestions(analysis)
    except Exception:
        logger.exception('[AILearning] Falha na sugestão antes da migração conv=%s', conversation_id)
