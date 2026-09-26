"""
Rotina noturna: conversas encerradas até a meia-noite vão ao Supabase e saem do banco local.

Durante o dia as encerradas ficam no local (DEFER_CLOSED_MIGRATION) para a IA analisar.
O loop periódico do Daphne chama `maybe_start_nightly_migration()` a cada minuto; a rotina roda
sempre que existir encerrada de um dia anterior, então se a stack estava fora às 00:00 ela
recupera o atraso assim que voltar.

- Thread própria, em lotes: não segura o loop periódico (finalize_closing, cobrança).
- pg_try_advisory_lock: só um processo/réplica migra por vez.
- CSAT enviado há pouco fica para a próxima passada (resposta do cliente ainda pode chegar).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

from django.db import close_old_connections, connection
from django.utils import timezone

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
CSAT_WAIT = timedelta(hours=2)
# Após a meia-noite a rotina tem essa folga antes do boletim de saúde acusar migração atrasada
HEALTH_GRACE = timedelta(hours=2)
RETRY_AFTER_FAILURE_SECONDS = 1800
_ADVISORY_LOCK_KEY = 7_302_026_001

_thread_lock = threading.Lock()
_running = False
_next_allowed_at = 0.0


def local_midnight(now=None):
    """00:00 de hoje no fuso do sistema (aware)."""
    now_local = timezone.localtime(now or timezone.now())
    return now_local.replace(hour=0, minute=0, second=0, microsecond=0)


def closed_before(cutoff):
    """Encerradas (status closed) cujo encerramento foi antes de `cutoff`."""
    from django.db.models import DateTimeField
    from django.db.models.fields.json import KeyTextTransform
    from django.db.models.functions import Cast, Coalesce
    from conversations.models import Conversation

    return (
        Conversation.objects.filter(status='closed')
        .annotate(
            _closed_at=Coalesce(
                Cast(KeyTextTransform('closed_at', 'additional_attributes'), DateTimeField()),
                'updated_at',
            )
        )
        .filter(_closed_at__lt=cutoff)
    )


def pending_migration_cutoff(now=None):
    """Encerradas antes deste instante já deveriam ter ido ao Supabase (boletim de saúde)."""
    now = now or timezone.now()
    midnight = local_midnight(now)
    if timezone.localtime(now) - midnight < HEALTH_GRACE:
        return midnight - timedelta(days=1)
    return midnight


def _candidates(cutoff, skip_ids):
    from conversations.models import CSATRequest

    waiting_csat = CSATRequest.objects.filter(
        status__in=['pending', 'sent'],
        created_at__gte=timezone.now() - CSAT_WAIT,
    ).values('conversation_id')
    return (
        closed_before(cutoff)
        .exclude(id__in=waiting_csat)
        .exclude(id__in=skip_ids)
        .order_by('id')
        .values_list('id', flat=True)[:BATCH_SIZE]
    )


def _try_advisory_lock() -> bool:
    if connection.vendor != 'postgresql':
        return True
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [_ADVISORY_LOCK_KEY])
        return bool(cursor.fetchone()[0])


def _advisory_unlock() -> None:
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_unlock(%s)', [_ADVISORY_LOCK_KEY])


def run_nightly_migration() -> dict:
    """Migra todas as encerradas antes da meia-noite de hoje, em lotes. Retorna estatísticas."""
    from conversations.models import CSATRequest
    from core.chat_migration_service import chat_migration_service

    stats = {'migrated': 0, 'failed': 0, 'locked': False}
    if not _try_advisory_lock():
        stats['locked'] = True
        return stats
    try:
        cutoff = local_midnight()
        failed_ids = set()
        while True:
            batch = list(_candidates(cutoff, failed_ids))
            if not batch:
                break
            for conversation_id in batch:
                try:
                    # CSAT antigo ainda aberto não recebe mais resposta; sem isso a conversa ficaria presa
                    CSATRequest.objects.filter(
                        conversation_id=conversation_id, status__in=['pending', 'sent'],
                    ).update(status='expired')
                    result = chat_migration_service.encerrar_e_migrar(
                        conversation_id,
                        metadata={'migrado_rotina_noturna': True},
                        force=True,
                    )
                except Exception:
                    logger.exception('[NightlyMigration] Erro na conversa %s', conversation_id)
                    result = {}
                if result.get('removed_from_local'):
                    stats['migrated'] += 1
                else:
                    failed_ids.add(conversation_id)
                    stats['failed'] += 1
                    logger.warning(
                        '[NightlyMigration] Conversa %s não migrada (fica no local): %s',
                        conversation_id, result.get('errors') or result.get('warnings'),
                    )
    finally:
        try:
            _advisory_unlock()
        except Exception:
            logger.exception('[NightlyMigration] Falha ao liberar trava')
    return stats


def _thread_main() -> None:
    global _running, _next_allowed_at
    close_old_connections()
    retry_later = False
    try:
        stats = run_nightly_migration()
        retry_later = bool(stats['failed'])
        if stats['migrated'] or stats['failed']:
            logger.info('[NightlyMigration] concluída: %s', stats)
    except Exception:
        retry_later = True
        logger.exception('[NightlyMigration] erro')
    finally:
        close_old_connections()
        with _thread_lock:
            _running = False
            if retry_later:
                _next_allowed_at = time.monotonic() + RETRY_AFTER_FAILURE_SECONDS


def maybe_start_nightly_migration() -> bool:
    """Dispara a rotina em thread se houver encerradas de dias anteriores (idempotente)."""
    global _running
    from core.chat_migration_service import defer_closed_migration

    if not defer_closed_migration():
        return False
    with _thread_lock:
        if _running or time.monotonic() < _next_allowed_at:
            return False
        if not closed_before(local_midnight()).exists():
            return False
        _running = True
    threading.Thread(target=_thread_main, name='niochat-nightly-migration', daemon=True).start()
    return True
