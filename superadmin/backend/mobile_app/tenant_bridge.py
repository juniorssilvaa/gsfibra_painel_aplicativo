"""Chamadas Superadmin → painel do provedor (tenant) para o canal do app."""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _is_loopback_or_local_url(url: str) -> bool:
    """URLs de desenvolvimento local — inválidas em produção."""
    raw = (url or '').strip().lower()
    if not raw:
        return False
    try:
        host = (urlparse(raw).hostname or '').strip().lower()
    except Exception:
        host = ''
    if not host:
        # fallback textual
        return any(
            token in raw
            for token in (
                '://127.0.0.1',
                '://localhost',
                '://0.0.0.0',
                '://[::1]',
            )
        )
    return host in ('127.0.0.1', 'localhost', '0.0.0.0', '::1') or host.endswith('.local')


def _subdomain_base_url(provedor) -> Optional[str]:
    subdomain = (getattr(provedor, 'subdomain', None) or '').strip().rstrip('/')
    if not subdomain:
        return None
    if subdomain.startswith('http://') or subdomain.startswith('https://'):
        return subdomain.rstrip('/')
    if '.' not in subdomain:
        subdomain = f'{subdomain}.niohub.com.br'
    return f'https://{subdomain}'


def tenant_base_url(provedor) -> Optional[str]:
    """
    Resolve a URL do painel do provedor para webhooks do app.

    Em produção NUNCA usa 127.0.0.1/localhost quando o provedor tem subdomínio —
    isso quebrava o chat do app (TENANT_WEBHOOK_BASE_URL / painel_url de dev).
    """
    debug = bool(getattr(settings, 'DEBUG', False))
    subdomain_url = _subdomain_base_url(provedor)

    extras = provedor.integracoes_externas if isinstance(getattr(provedor, 'integracoes_externas', None), dict) else {}
    explicit = (
        (extras or {}).get('painel_url')
        or (extras or {}).get('tenant_url')
        or ''
    ).strip().rstrip('/')

    if explicit:
        if _is_loopback_or_local_url(explicit):
            if debug:
                return explicit
            if subdomain_url:
                logger.warning(
                    '[app-mobile] Ignorando painel_url/tenant_url local (%s) do provedor %s — usando %s.',
                    explicit,
                    getattr(provedor, 'id', None),
                    subdomain_url,
                )
                return subdomain_url
            logger.warning(
                '[app-mobile] painel_url local (%s) sem subdomínio no provedor %s.',
                explicit,
                getattr(provedor, 'id', None),
            )
        else:
            return explicit

    fallback = (getattr(settings, 'TENANT_WEBHOOK_BASE_URL', '') or '').strip().rstrip('/')
    if fallback:
        if _is_loopback_or_local_url(fallback):
            # Em desenvolvimento o painel do provedor roda local; em produção, nunca.
            if debug:
                return fallback
            if subdomain_url:
                return subdomain_url
        elif debug:
            return fallback

    return subdomain_url


def tenant_auth_headers(provedor) -> dict:
    token = (getattr(provedor, 'integration_token', None) or '').strip()
    if not token:
        return {}
    return {'Authorization': f'Bearer {token}'}


def post_tenant_app_mobile(provedor, payload: dict, files=None, timeout=30, path: str = ''):
    """
    Encaminha mensagem inbound do app para o painel do provedor.
    POST /api/webhooks/app-mobile/{path}
    """
    base = tenant_base_url(provedor)
    if not base:
        return False, 'Painel do provedor sem URL (subdomínio / painel_url).', None
    headers = tenant_auth_headers(provedor)
    if not headers:
        return False, 'Token de integração do provedor não configurado.', None
    url = f'{base}/api/webhooks/app-mobile/{path}'
    try:
        if files:
            resp = requests.post(url, data=payload, files=files, headers=headers, timeout=timeout)
        else:
            headers = {**headers, 'Content-Type': 'application/json'}
            resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning('[app-mobile] Falha ao chamar tenant %s: %s', url, exc)
        return False, f'Falha ao contactar o painel de atendimento: {exc}', None

    try:
        body = resp.json()
    except ValueError:
        body = {'raw': (resp.text or '')[:500]}

    if not resp.ok:
        err = body.get('error') if isinstance(body, dict) else None
        logger.warning('[app-mobile] Tenant %s HTTP %s %s', url, resp.status_code, (resp.text or '')[:300])
        return False, err or f'Painel retornou HTTP {resp.status_code}', body
    return True, None, body


def get_tenant_app_mobile_messages(provedor, cpf: str, after_id=None, timeout=20):
    base = tenant_base_url(provedor)
    if not base:
        return False, 'Painel do provedor sem URL (subdomínio / painel_url).', None
    headers = tenant_auth_headers(provedor)
    if not headers:
        return False, 'Token de integração do provedor não configurado.', None
    url = f'{base}/api/webhooks/app-mobile/messages/'
    params = {'cpf': cpf, 'provedor_id': provedor.id}
    if after_id:
        params['after_id'] = after_id
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        logger.warning('[app-mobile] Falha ao listar mensagens no tenant %s: %s', url, exc)
        return False, f'Falha ao contactar o painel de atendimento: {exc}', None

    try:
        body = resp.json()
    except ValueError:
        body = {'raw': (resp.text or '')[:500]}

    if not resp.ok:
        err = body.get('error') if isinstance(body, dict) else None
        logger.warning(
            '[app-mobile] Tenant GET %s HTTP %s %s',
            url,
            resp.status_code,
            (resp.text or '')[:300],
        )
        return False, err or f'Painel retornou HTTP {resp.status_code}', body
    return True, None, body
