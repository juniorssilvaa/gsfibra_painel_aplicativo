"""
Envia mensagens do sistema do Superadmin para o banco de cada tenant (VPS).
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from django.utils import timezone

from .models import Provedor

logger = logging.getLogger(__name__)


def _tenant_host(provedor: Provedor) -> str | None:
    subdomain = (getattr(provedor, 'subdomain', '') or '').strip()
    if not subdomain:
        return None
    if '.' not in subdomain:
        subdomain = f'{subdomain}.niohub.com.br'
    return subdomain.rstrip('/')


def push_system_message_to_tenant(provedor: Provedor, payload: dict[str, Any]) -> dict[str, Any]:
    """
    POST no webhook do tenant. Retorna dict com ok, status_code, error.
    """
    host = _tenant_host(provedor)
    if not host:
        return {
            'provedor_id': provedor.id,
            'ok': False,
            'error': 'Provedor sem subdomínio configurado',
        }

    token = (getattr(provedor, 'integration_token', '') or '').strip()
    if not token:
        return {
            'provedor_id': provedor.id,
            'ok': False,
            'error': 'Provedor sem token de integração',
        }

    url = f'https://{host}/api/webhooks/admin/system-message/'
    headers = {'Authorization': f'Bearer {token}'}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.ok:
            try:
                body = resp.json()
            except Exception:
                body = {}
            provedor.integration_token_last_used_at = timezone.now()
            provedor.save(update_fields=['integration_token_last_used_at'])
            return {
                'provedor_id': provedor.id,
                'ok': True,
                'tenant_message_id': body.get('id'),
            }
        return {
            'provedor_id': provedor.id,
            'ok': False,
            'status_code': resp.status_code,
            'error': (resp.text or '')[:300],
        }
    except requests.RequestException as exc:
        logger.warning(
            '[system-message] Falha ao contactar tenant %s (provedor %s): %s',
            host,
            provedor.id,
            exc,
        )
        return {
            'provedor_id': provedor.id,
            'ok': False,
            'error': str(exc),
        }


def dispatch_system_message_to_tenants(mensagem, provedor_ids: list[int]) -> list[dict[str, Any]]:
    """Envia a mesma mensagem para cada provedor selecionado (cada VPS/tenant)."""
    results: list[dict[str, Any]] = []
    clean_ids: list[int] = []
    for pid in provedor_ids or []:
        try:
            clean_ids.append(int(pid))
        except (TypeError, ValueError):
            continue

    base_payload = {
        'superadmin_message_id': mensagem.id,
        'assunto': mensagem.assunto or '',
        'mensagem': mensagem.mensagem or '',
        'tipo': mensagem.tipo or 'notificacao',
        'visivel_para_agentes': bool(mensagem.visivel_para_agentes),
    }

    for pid in clean_ids:
        provedor = Provedor.objects.filter(id=pid).first()
        if not provedor:
            results.append({
                'provedor_id': pid,
                'ok': False,
                'error': 'Provedor não encontrado no superadmin',
            })
            continue

        payload = {
            **base_payload,
            'provedor_id': pid,
            'provedores': [pid],
        }
        result = push_system_message_to_tenant(provedor, payload)
        results.append(result)
        if result.get('ok'):
            logger.info(
                '[system-message] Mensagem %s entregue ao tenant do provedor %s (id tenant=%s)',
                mensagem.id,
                pid,
                result.get('tenant_message_id'),
            )
        else:
            logger.warning(
                '[system-message] Falha ao entregar mensagem %s ao provedor %s: %s',
                mensagem.id,
                pid,
                result.get('error'),
            )

    return results
