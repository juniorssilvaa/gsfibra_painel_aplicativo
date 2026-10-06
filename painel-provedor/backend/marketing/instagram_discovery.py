"""Perfis públicos de concorrentes no Instagram via Business Discovery (API oficial da Meta).

Usa uma conta Instagram profissional da NioHub (ligada a uma Página do Facebook) e um token de usuário do
sistema com instagram_basic + pages_show_list (+ business_management). A conta consultada precisa ser
profissional (comercial ou criador).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

import requests
from django.conf import settings
from django.core.cache import cache

GRAPH_URL = 'https://graph.facebook.com/v21.0'
CACHE_SECONDS = 6 * 60 * 60
MAX_POSTS = 12
MAX_MEDIA_BYTES = 8 * 1024 * 1024
_USERNAME_RE = re.compile(r'^[A-Za-z0-9._]{1,30}$')

NOT_CONFIGURED_MSG = (
    'A análise de Instagram ainda não está ativada neste servidor: falta configurar META_DISCOVERY_IG_USER_ID e '
    'META_DISCOVERY_ACCESS_TOKEN. Enquanto isso, o dono pode colar prints das postagens no Estúdio.'
)


class DiscoveryError(Exception):
    pass


def normalize_username(value: str) -> str:
    raw = (value or '').strip()
    match = re.search(r'instagram\.com/([^/?#]+)', raw)
    if match:
        raw = match.group(1)
    raw = raw.lstrip('@').strip().strip('/')
    if not _USERNAME_RE.match(raw):
        raise DiscoveryError(f'"{value}" não parece um usuário do Instagram válido.')
    return raw.lower()


def discovery_config() -> Tuple[str, str]:
    ig_user_id = (getattr(settings, 'META_DISCOVERY_IG_USER_ID', '') or '').strip()
    token = (getattr(settings, 'META_DISCOVERY_ACCESS_TOKEN', '') or '').strip() or (
        getattr(settings, 'WHATSAPP_SYSTEM_USER_TOKEN', '') or ''
    ).strip()
    if not ig_user_id or not token:
        raise DiscoveryError(NOT_CONFIGURED_MSG)
    return ig_user_id, token


def _friendly_graph_error(error: Dict[str, Any], username: str) -> str:
    message = str(error.get('message') or '')
    code = error.get('code')
    lowered = message.lower()
    if 'cannot find user' in lowered or error.get('error_subcode') == 2207013 or code == 110:
        return (
            f'Não encontrei @{username} como perfil profissional público. A Meta só libera a leitura de contas '
            'comerciais ou de criador; perfis pessoais ou privados não aparecem.'
        )
    if code in (4, 17, 32, 613):
        return 'Limite de consultas da Meta atingido. Tente de novo em alguns minutos.'
    if code == 190:
        return 'O token da NioHub para análise de Instagram expirou ou foi revogado. Avise o suporte NioHub.'
    if code in (10, 200) or 'permission' in lowered:
        return 'O token da NioHub para análise de Instagram não tem as permissões necessárias. Avise o suporte NioHub.'
    return f'A Meta recusou a consulta: {message[:200]}'


def fetch_profile(username: str, limit: int = MAX_POSTS) -> Dict[str, Any]:
    username = normalize_username(username)
    limit = max(1, min(int(limit or MAX_POSTS), MAX_POSTS))
    cache_key = f'mkt:igdisc:{username}:{limit}'
    cached = cache.get(cache_key)
    if cached:
        return cached
    ig_user_id, token = discovery_config()
    media_fields = 'caption,media_type,media_product_type,media_url,permalink,like_count,comments_count,timestamp'
    fields = (
        f'business_discovery.username({username})'
        f'{{username,name,biography,website,followers_count,follows_count,media_count,'
        f'media.limit({limit}){{{media_fields}}}}}'
    )
    try:
        resp = requests.get(f'{GRAPH_URL}/{ig_user_id}', params={'fields': fields, 'access_token': token}, timeout=30)
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise DiscoveryError(f'Não consegui falar com a Meta agora: {exc}') from exc
    if data.get('error'):
        raise DiscoveryError(_friendly_graph_error(data['error'], username))
    profile = data.get('business_discovery') or {}
    if not profile:
        raise DiscoveryError(f'A Meta não retornou dados de @{username}.')
    media = profile.get('media') or []
    if isinstance(media, dict):
        media = media.get('data') or []
    profile = {**profile, 'media': media}
    cache.set(cache_key, profile, CACHE_SECONDS)
    return profile


def download_media(url: str) -> Optional[bytes]:
    if not url:
        return None
    try:
        with requests.get(url, timeout=30, stream=True) as resp:
            if resp.status_code != 200 or not resp.headers.get('content-type', '').startswith('image/'):
                return None
            chunks, size = [], 0
            for chunk in resp.iter_content(64 * 1024):
                size += len(chunk)
                if size > MAX_MEDIA_BYTES:
                    return None
                chunks.append(chunk)
            return b''.join(chunks)
    except requests.RequestException:
        return None
