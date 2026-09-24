"""
Modo manutenção do tenant (ligado pelo Superadmin durante a atualização da stack).

O estado fica no Redis da stack (persistente entre recriações de container) com TTL,
para que nunca fique preso caso o Superadmin não consiga desligar ao final.
"""
import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

PROCESS_STARTED_AT = int(time.time())

MAINTENANCE_KEY = 'niohub:maintenance'
DEFAULT_TTL_SECONDS = 20 * 60
MAX_TTL_SECONDS = 2 * 60 * 60

_local_state = {'value': None, 'expires_at': 0.0}
_redis_client = None


def _redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    url = getattr(settings, 'REDIS_URL', '') or ''
    if not url:
        return None
    try:
        import redis
        _redis_client = redis.from_url(url, socket_timeout=1, socket_connect_timeout=1, decode_responses=True)
        return _redis_client
    except Exception as exc:
        logger.debug('[maintenance] Redis indisponível: %s', exc)
        return None


def get_state():
    raw = None
    conn = _redis()
    if conn is not None:
        try:
            raw = conn.get(MAINTENANCE_KEY)
        except Exception as exc:
            logger.debug('[maintenance] leitura Redis falhou: %s', exc)
            conn = None
    if conn is None and _local_state['expires_at'] > time.time():
        raw = _local_state['value']

    if not raw:
        return {'active': False}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {'active': False}
    return {
        'active': True,
        'message': data.get('message') or '',
        'since': data.get('since'),
    }


def health_payload():
    """Corpo do /api/health/ (usado pela view e pelos middlewares que respondem direto)."""
    return {'status': 'ok', 'maintenance': get_state(), 'boot': PROCESS_STARTED_AT}


def set_state(active, message='', ttl_seconds=None):
    ttl = DEFAULT_TTL_SECONDS
    if ttl_seconds:
        try:
            ttl = max(60, min(int(ttl_seconds), MAX_TTL_SECONDS))
        except (TypeError, ValueError):
            ttl = DEFAULT_TTL_SECONDS

    payload = json.dumps({'message': (message or '')[:500], 'since': int(time.time())})
    if active:
        _local_state.update(value=payload, expires_at=time.time() + ttl)
    else:
        _local_state.update(value=None, expires_at=0.0)

    conn = _redis()
    if conn is None:
        return False
    try:
        if active:
            conn.set(MAINTENANCE_KEY, payload, ex=ttl)
        else:
            conn.delete(MAINTENANCE_KEY)
        return True
    except Exception as exc:
        logger.warning('[maintenance] gravação Redis falhou: %s', exc)
        return False
