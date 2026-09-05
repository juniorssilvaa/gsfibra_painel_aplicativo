"""Chamadas Superadmin → painel do provedor (tenant) para o canal do app."""
from __future__ import annotations

import logging
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def tenant_base_url(provedor) -> Optional[str]:
    extras = provedor.integracoes_externas if isinstance(getattr(provedor, 'integracoes_externas', None), dict) else {}
    explicit = (
        (extras or {}).get('painel_url')
        or (extras or {}).get('tenant_url')
        or ''
    ).strip().rstrip('/')
    if explicit:
        return explicit

    # Em dev local, TENANT_WEBHOOK_BASE_URL (ex. http://127.0.0.1:8011) tem prioridade
    # sobre o subdomínio de produção — evita 502 quando o DNS do tenant não resolve.
    fallback = (getattr(settings, 'TENANT_WEBHOOK_BASE_URL', '') or '').strip().rstrip('/')
    if fallback and getattr(settings, 'DEBUG', False):
        return fallback

    subdomain = (getattr(provedor, 'subdomain', None) or '').strip().rstrip('/')
    if subdomain:
        if subdomain.startswith('http://') or subdomain.startswith('https://'):
            return subdomain
        if '.' not in subdomain:
            subdomain = f'{subdomain}.niohub.com.br'
        return f'https://{subdomain}'

    return None


def tenant_auth_headers(provedor) -> dict:
    token = (getattr(provedor, 'integration_token', None) or '').strip()
    if not token:
        return {}
    return {'Authorization': f'Bearer {token}'}


def post_tenant_app_mobile(provedor, payload: dict, files=None, timeout=30):
    """
    Encaminha mensagem inbound do app para o painel do provedor.
    POST /api/webhooks/app-mobile/
    """
    base = tenant_base_url(provedor)
    if not base:
        return False, 'Painel do provedor sem URL (subdomínio / painel_url).', None
    headers = tenant_auth_headers(provedor)
    if not headers:
        return False, 'Token de integração do provedor não configurado.', None
    url = f'{base}/api/webhooks/app-mobile/'
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
