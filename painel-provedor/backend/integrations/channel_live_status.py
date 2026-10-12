"""
Status real (Meta) e foto de perfil dos canais, consumidos pelo Superadmin.

As URLs de foto da Meta expiram e bloqueiam hotlink, por isso a imagem é baixada
aqui (com o token do canal, que só existe no tenant) e devolvida como data URI.
"""
from __future__ import annotations

import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

import requests
from django.core.cache import cache
from django.db import connection

logger = logging.getLogger(__name__)

GRAPH_FB = 'https://graph.facebook.com/v21.0'
GRAPH_IG = 'https://graph.instagram.com/v21.0'
CACHE_TTL = 300
MAX_PICTURE_BYTES = 400 * 1024


def _cache_key(canal) -> str:
    return f'channel_live_status:{canal.id}'


def _picture_data_uri(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException:
        return None
    content_type = (resp.headers.get('Content-Type') or '').split(';')[0].strip()
    if resp.status_code != 200 or not content_type.startswith('image/') or len(resp.content) > MAX_PICTURE_BYTES:
        return None
    return f'data:{content_type};base64,{base64.b64encode(resp.content).decode("ascii")}'


def _whatsapp_oficial(canal) -> Dict[str, Any]:
    from integrations.whatsapp_oficial_status import verify_whatsapp_oficial_connection

    result = verify_whatsapp_oficial_connection(canal)
    info: Dict[str, Any] = {
        'connected': result.get('connected') if result.get('ok') else None,
        'display_name': result.get('verified_name') or '',
        'display_phone': result.get('display_phone_number') or canal.phone_number or '',
        'error': result.get('error_message') or result.get('error') or '',
    }
    if info['connected']:
        try:
            resp = requests.get(
                f'{GRAPH_FB}/{canal.phone_number_id}/whatsapp_business_profile',
                params={'fields': 'profile_picture_url'},
                headers={'Authorization': f'Bearer {canal.token}'},
                timeout=10,
            )
            if resp.ok:
                data = (resp.json() or {}).get('data') or [{}]
                info['profile_picture'] = _picture_data_uri(data[0].get('profile_picture_url'))
        except (requests.RequestException, ValueError):
            pass
    return info


def _instagram(canal) -> Dict[str, Any]:
    if not canal.token:
        return {'connected': False, 'error': 'missing_credentials'}
    try:
        resp = requests.get(
            f'{GRAPH_IG}/me',
            params={'fields': 'user_id,username,name,profile_picture_url', 'access_token': canal.token},
            timeout=15,
        )
    except requests.RequestException as exc:
        return {'connected': None, 'error': f'network_error: {exc.__class__.__name__}'}

    if resp.ok:
        data = resp.json() or {}
        return {
            'connected': True,
            'display_name': data.get('name') or '',
            'username': data.get('username') or '',
            'profile_picture': _picture_data_uri(data.get('profile_picture_url')),
        }
    try:
        message = ((resp.json() or {}).get('error') or {}).get('message') or ''
    except ValueError:
        message = ''
    return {'connected': False, 'error': message or f'HTTP {resp.status_code}'}


def _local(canal) -> Dict[str, Any]:
    return {
        'connected': bool(canal.ativo) and (canal.status or 'connected') == 'connected',
        'source': 'local',
    }


def channel_live_status(canal, *, refresh: bool = False) -> Dict[str, Any]:
    key = _cache_key(canal)
    if not refresh:
        cached = cache.get(key)
        if cached is not None:
            return cached

    base = {
        'id': canal.id,
        'tipo': canal.tipo,
        'nome': canal.nome or '',
        'phone_number_id': canal.phone_number_id or '',
        'waba_id': canal.waba_id or '',
        'instagram_user_id': str((canal.dados_extras or {}).get('instagram_user_id') or ''),
        'source': 'meta',
    }
    try:
        if canal.tipo == 'whatsapp_oficial':
            base.update(_whatsapp_oficial(canal))
        elif canal.tipo == 'instagram':
            base.update(_instagram(canal))
        else:
            base.update(_local(canal))
    except Exception as exc:
        logger.warning('[channel-live-status] Falha no canal %s: %s', canal.id, exc)
        base.update({'connected': None, 'error': str(exc)[:200]})

    cache.set(_cache_key(canal), base, CACHE_TTL)
    return base


def all_channels_live_status(*, refresh: bool = False):
    from core.models import Canal

    canais = list(Canal.objects.exclude(tipo='app_mobile').order_by('id'))
    if not canais:
        return []

    def _worker(canal):
        try:
            return channel_live_status(canal, refresh=refresh)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=min(len(canais), 6)) as pool:
        return list(pool.map(_worker, canais))
