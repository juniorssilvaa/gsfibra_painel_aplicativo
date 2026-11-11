"""
Status real dos canais (Conectado/Desconectado + foto) consultando cada tenant.

O token Meta de cada canal só existe no tenant, então o superadmin pergunta ao
webhook /api/webhooks/admin/channels-status/ de cada provedor e casa o resultado
com os canais espelhados aqui.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

import requests
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)

CACHE_TTL = 120


def _fetch_tenant_channels(provedor, *, refresh: bool) -> Tuple[Optional[List[dict]], Optional[str]]:
    from super_core.views import _tenant_admin_url

    key = f'tenant_channels_status:{provedor.id}'
    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached, None

    token = (provedor.integration_token or '').strip()
    url = _tenant_admin_url(provedor, 'channels-status')
    if not url or not token:
        return None, 'Provedor sem subdomínio ou token de integração'
    try:
        resp = requests.get(
            url,
            params={'refresh': '1'} if refresh else None,
            headers={'Authorization': f'Bearer {token}'},
            timeout=40,
        )
    except requests.RequestException as exc:
        return None, f'Falha ao contactar o painel: {exc.__class__.__name__}'
    if not resp.ok:
        return None, f'Painel respondeu HTTP {resp.status_code}'
    try:
        channels = (resp.json() or {}).get('channels') or []
    except ValueError:
        return None, 'Resposta inválida do painel'
    cache.set(key, channels, CACHE_TTL)
    return channels, None


def _match(canal, tenant_channels: List[dict]) -> Optional[dict]:
    extras = canal.dados_extras or {}
    same_type = [t for t in tenant_channels if t.get('tipo') == canal.tipo]

    for field in ('phone_number_id', 'waba_id'):
        value = str(getattr(canal, field, '') or '').strip()
        if value:
            found = next((t for t in same_type if str(t.get(field) or '') == value), None)
            if found:
                return found

    ig_id = str(extras.get('instagram_user_id') or '').strip()
    if ig_id:
        found = next((t for t in same_type if str(t.get('instagram_user_id') or '') == ig_id), None)
        if found:
            return found

    tenant_id = str(extras.get('tenant_canal_id') or '').strip()
    if tenant_id:
        found = next((t for t in same_type if str(t.get('id')) == tenant_id), None)
        if found:
            return found

    return same_type[0] if len(same_type) == 1 else None


def canais_live_status(canais, *, refresh: bool = False) -> Dict[str, dict]:
    """Retorna {canal_id_superadmin: {connected, profile_picture, ...}}."""
    canais = list(canais)
    provedores = {c.provedor_id: c.provedor for c in canais if c.provedor_id}
    if not provedores:
        return {}

    def _worker(provedor):
        try:
            return provedor.id, *_fetch_tenant_channels(provedor, refresh=refresh)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=min(len(provedores), 10)) as pool:
        results = {pid: (channels, error) for pid, channels, error in pool.map(_worker, provedores.values())}

    status_by_canal = {}
    for canal in canais:
        channels, error = results.get(canal.provedor_id, (None, 'Provedor não consultado'))
        if channels is None:
            status_by_canal[str(canal.id)] = {'connected': None, 'error': error}
            continue
        found = _match(canal, channels)
        if not found:
            status_by_canal[str(canal.id)] = {'connected': None, 'error': 'Canal não encontrado no painel do provedor'}
            continue
        status_by_canal[str(canal.id)] = {
            'connected': found.get('connected'),
            'profile_picture': found.get('profile_picture'),
            'display_name': found.get('display_name') or '',
            'username': found.get('username') or '',
            'source': found.get('source') or 'meta',
            'error': found.get('error') or '',
        }
    return status_by_canal
