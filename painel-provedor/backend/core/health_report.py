"""
Boletim de saúde do tenant enviado ao Superadmin junto do heartbeat de versão.

Cada métrica é isolada: falha em uma não impede o envio das demais.
"""
import collections
import logging
import os
import shutil
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

ERROR_WINDOW_SECONDS = 3600
RECENT_ERRORS_LIMIT = 5
PENDING_MIGRATION_AFTER_MINUTES = 15


class _ErrorCounter(logging.Handler):
    """Guarda horário e mensagem curta dos logs ERROR+ da última hora (só em memória)."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self._events = collections.deque(maxlen=2000)
        self._lock_events = threading.Lock()

    def emit(self, record):
        try:
            msg = f'{record.name}: {record.getMessage()}'[:300]
        except Exception:
            msg = record.name
        with self._lock_events:
            self._events.append((time.time(), msg))

    def snapshot(self):
        cutoff = time.time() - ERROR_WINDOW_SECONDS
        with self._lock_events:
            recent = [(ts, msg) for ts, msg in self._events if ts >= cutoff]
        return {
            'errors_last_hour': len(recent),
            'recent_errors': [
                {'at': int(ts), 'message': msg} for ts, msg in recent[-RECENT_ERRORS_LIMIT:]
            ],
        }


_counter = None


def install_error_counter():
    """Idempotente: anexa o contador ao logger raiz do processo atual."""
    global _counter
    if _counter is None:
        _counter = _ErrorCounter()
        logging.getLogger().addHandler(_counter)
    return _counter


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:
        logger.debug('[health] métrica %s falhou: %s', getattr(fn, '__name__', '?'), exc)
        return default


def _iso(dt):
    return dt.isoformat() if dt else None


def _channels():
    from core.models import Canal
    return [
        {
            'id': c.id,
            'tipo': c.tipo,
            'nome': c.nome,
            'status': c.status,
            'somente_disparo': c.somente_disparo,
        }
        for c in Canal.objects.filter(ativo=True).only('id', 'tipo', 'nome', 'status', 'somente_disparo')
    ]


def _conversations():
    from conversations.models import Conversation, Message
    active = Conversation.objects.exclude(status='closed')
    pending_cutoff = timezone.now() - timedelta(minutes=PENDING_MIGRATION_AFTER_MINUTES)
    last_inbound = (
        Message.objects.filter(is_from_customer=True).order_by('-created_at').values_list('created_at', flat=True).first()
    )
    return {
        'open': active.count(),
        'waiting_agent': active.filter(waiting_for_agent=True, assignee__isnull=True).count(),
        'pending_migration': Conversation.objects.filter(status='closed', updated_at__lt=pending_cutoff).count(),
        'last_inbound_at': _iso(last_inbound),
    }


def _disk():
    path = str(getattr(settings, 'MEDIA_ROOT', '') or '/')
    if not os.path.isdir(path):
        path = '/'
    usage = shutil.disk_usage(path)
    return {
        'total_gb': round(usage.total / 1024 ** 3, 1),
        'used_gb': round(usage.used / 1024 ** 3, 1),
        'used_percent': round(usage.used * 100 / usage.total, 1) if usage.total else None,
    }


def _database_mb():
    from django.db import connection
    if connection.vendor != 'postgresql':
        return None
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_database_size(current_database())')
        return round(cursor.fetchone()[0] / 1024 ** 2, 1)


def build_health_report():
    from core.maintenance import PROCESS_STARTED_AT, get_state

    report = {
        'generated_at': int(time.time()),
        'boot': PROCESS_STARTED_AT,
        'maintenance': _safe(lambda: bool(get_state().get('active')), False),
        'channels': _safe(_channels, []),
        'conversations': _safe(_conversations, {}),
        'disk': _safe(_disk, {}),
        'database_mb': _safe(_database_mb),
    }
    report.update(_counter.snapshot() if _counter else {'errors_last_hour': None, 'recent_errors': []})
    return report
