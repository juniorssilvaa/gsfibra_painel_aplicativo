"""Painel de saúde dos provedores: consolida heartbeat + boletim + deploys em verde/amarelo/vermelho."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone as dt_timezone

import requests
from django.utils import timezone

from super_core.services.tenant_maintenance import _tenant_host

GREEN, YELLOW, RED = 'green', 'yellow', 'red'
_RANK = {GREEN: 0, YELLOW: 1, RED: 2}

HEARTBEAT_WARN_MIN = 7
HEARTBEAT_DOWN_MIN = 15
DISK_WARN, DISK_CRIT = 80, 90
ERRORS_WARN, ERRORS_CRIT = 10, 50
PENDING_MIGRATION_CRIT = 20
INBOUND_SILENCE_HOURS = 24
_BAD_CHANNEL_STATUS = ('disconnect', 'desconect', 'error', 'erro', 'offline', 'closed', 'close', 'inactive', 'banned', 'expired')
_MESSAGING_TYPES = ('whatsapp', 'whatsapp_session', 'whatsapp_oficial', 'telegram', 'instagram')


def _version_tuple(value):
    return tuple(int(p) for p in re.findall(r'\d+', str(value or ''))[:3]) or None


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=dt_timezone.utc)


def expected_versions():
    from super_core.models import SystemUpdate
    from super_core.services.app_version import read_app_version

    stable = (
        SystemUpdate.objects.filter(channel='stable', is_deployed=True)
        .order_by('-release_date').values_list('version', flat=True).first()
    )
    return {'stable': stable or None, 'beta': read_app_version() or None}


def last_deploys_by_provider(limit_updates=40):
    from super_core.models import SystemUpdate

    result = {}
    for update in SystemUpdate.objects.order_by('-release_date')[:limit_updates]:
        for row in update.results or []:
            pid = row.get('id')
            if pid is None or pid in result:
                continue
            result[pid] = {
                'version': update.version,
                'channel': update.channel,
                'status': row.get('status'),
                'message': row.get('msg') or '',
                'at': (update.finished_at or update.started_at or update.release_date).isoformat(),
            }
    return result


def evaluate(provedor, health, expected, last_deploy, now=None):
    now = now or timezone.now()
    reasons = []

    def add(level, text):
        reasons.append({'level': level, 'text': text})

    data = (health.data if health else None) or {}
    last_seen = health.reported_at if health else provedor.integration_token_last_used_at
    minutes_since = int((now - last_seen).total_seconds() // 60) if last_seen else None

    if last_seen is None:
        add(RED, 'Nunca enviou sinal de vida')
    elif minutes_since >= HEARTBEAT_DOWN_MIN:
        add(RED, f'Sem sinal há {minutes_since} min')
    elif minutes_since >= HEARTBEAT_WARN_MIN:
        add(YELLOW, f'Sinal atrasado ({minutes_since} min)')

    if last_deploy and last_deploy.get('status') in ('failed', 'error'):
        add(RED, f"Último deploy ({last_deploy.get('version')}) falhou")

    exp = expected.get(provedor.release_channel)
    cur_t, exp_t = _version_tuple(provedor.current_version), _version_tuple(exp)
    if cur_t and exp_t and cur_t < exp_t:
        add(YELLOW, f'Versão {provedor.current_version} atrasada (canal {provedor.release_channel}: {exp})')

    if health is None:
        add(YELLOW, 'Sem boletim de saúde (painel em versão antiga)')
    else:
        if data.get('maintenance'):
            add(YELLOW, 'Em manutenção')

        channels = data.get('channels') or []
        messaging = [c for c in channels if c.get('tipo') in _MESSAGING_TYPES]
        if not messaging:
            add(YELLOW, 'Nenhum canal de atendimento ativo')
        for c in messaging:
            status = str(c.get('status') or '').lower()
            if any(bad in status for bad in _BAD_CHANNEL_STATUS):
                add(RED, f"Canal {c.get('nome') or c.get('tipo')} desconectado ({status})")

        conv = data.get('conversations') or {}
        last_inbound = _parse_dt(conv.get('last_inbound_at'))
        if last_inbound and any(not c.get('somente_disparo') for c in messaging):
            hours = int((now - last_inbound).total_seconds() // 3600)
            if hours >= INBOUND_SILENCE_HOURS:
                add(YELLOW, f'Nenhuma mensagem de cliente há {hours}h')

        pending = conv.get('pending_migration') or 0
        if pending:
            add(RED if pending > PENDING_MIGRATION_CRIT else YELLOW, f'{pending} conversa(s) encerrada(s) sem migrar ao Supabase')

        disk_pct = (data.get('disk') or {}).get('used_percent')
        if disk_pct is not None:
            if disk_pct >= DISK_CRIT:
                add(RED, f'Disco {disk_pct}% cheio')
            elif disk_pct >= DISK_WARN:
                add(YELLOW, f'Disco {disk_pct}% cheio')

        errors = data.get('errors_last_hour')
        if errors is not None:
            if errors >= ERRORS_CRIT:
                add(RED, f'{errors} erros na última hora')
            elif errors >= ERRORS_WARN:
                add(YELLOW, f'{errors} erros na última hora')

    status = max((r['level'] for r in reasons), key=_RANK.get, default=GREEN)
    return {
        'id': provedor.id,
        'nome': provedor.nome,
        'subdomain': provedor.subdomain,
        'vps': provedor.vps.name if provedor.vps_id and provedor.vps else None,
        'release_channel': provedor.release_channel,
        'current_version': provedor.current_version,
        'expected_version': exp,
        'last_seen_at': last_seen.isoformat() if last_seen else None,
        'minutes_since_seen': minutes_since,
        'last_update': provedor.last_update.isoformat() if provedor.last_update else None,
        'last_deploy': last_deploy,
        'health': data or None,
        'status': status,
        'reasons': sorted(reasons, key=lambda r: -_RANK[r['level']]),
    }


def health_overview():
    from super_core.models import Provedor

    expected = expected_versions()
    deploys = last_deploys_by_provider()
    now = timezone.now()
    providers = []
    for provedor in Provedor.objects.filter(is_active=True).select_related('vps', 'health'):
        health = getattr(provedor, 'health', None)
        providers.append(evaluate(provedor, health, expected, deploys.get(provedor.id), now))
    providers.sort(key=lambda p: (-_RANK[p['status']], p['nome'].lower()))
    summary = {level: sum(1 for p in providers if p['status'] == level) for level in (GREEN, YELLOW, RED)}
    return {'generated_at': now.isoformat(), 'expected_versions': expected, 'summary': summary, 'providers': providers}


def live_check(provedor):
    host = _tenant_host(provedor)
    if not host:
        return {'ok': False, 'error': 'Provedor sem subdomínio'}
    started = time.monotonic()
    try:
        resp = requests.get(f'https://{host}/api/health/', timeout=8)
    except Exception as exc:
        return {'ok': False, 'host': host, 'error': str(exc)[:200]}
    latency_ms = int((time.monotonic() - started) * 1000)
    body = {}
    try:
        body = resp.json() or {}
    except ValueError:
        pass
    return {
        'ok': resp.ok,
        'host': host,
        'status_code': resp.status_code,
        'latency_ms': latency_ms,
        'maintenance': bool((body.get('maintenance') or {}).get('active')) if isinstance(body.get('maintenance'), dict) else False,
        'boot': body.get('boot'),
    }
