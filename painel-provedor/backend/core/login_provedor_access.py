"""
Validação de acesso ao login do painel do provedor (suspensão superadmin / Asaas).
"""
from __future__ import annotations

import logging
import time
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_BLOCK_MESSAGE = (
    'Acesso suspenso pelo administrador do sistema. '
    'Entre em contato com o suporte ou regularize o pagamento.'
)

_CENTRAL_SYNC_CACHE: dict[int, Tuple[float, bool, str]] = {}
_CENTRAL_SYNC_TTL_SEC = 45
_LAST_SYNC_AT: dict[Tuple[int, ...], float] = {}


def collect_user_provedores(user) -> List:
    """Provedores ligados ao utilizador (FK ou M2M admin)."""
    from core.models import Provedor

    out: List[Provedor] = []
    seen = set()

    def _add(p):
        if p and p.id not in seen:
            seen.add(p.id)
            out.append(p)

    if getattr(user, 'provedor_id', None):
        try:
            _add(user.provedor)
        except Exception:
            pass
    elif hasattr(user, 'provedor') and user.provedor:
        _add(user.provedor)

    if hasattr(user, 'provedores_admin'):
        for p in user.provedores_admin.all():
            _add(p)

    return out


def resolve_central_provedor_id() -> Optional[int]:
    """Id do provedor no superadmin (pode diferir do id local no tenant)."""
    from core.provedor_id_mapping import configured_central_provedor_id

    pid = configured_central_provedor_id()
    if pid:
        return pid
    try:
        from core.support_account import resolve_provedor_id_from_superadmin

        return resolve_provedor_id_from_superadmin()
    except Exception as exc:
        logger.warning('[login] resolve_central_provedor_id: %s', exc)
        return None


def _reason_from_central(data: dict) -> str:
    sub = (data.get('subscription_status') or '').upper()
    status = (data.get('status') or '').lower()
    if sub == 'OVERDUE' or 'inadimpl' in status:
        return (
            'Sua fatura está em atraso. '
            'Efetue o pagamento para reativar o acesso ao painel.'
        )
    if status in ('suspenso', 'suspended', 'inativo', 'inactive'):
        return _DEFAULT_BLOCK_MESSAGE
    return _DEFAULT_BLOCK_MESSAGE


def _central_is_blocked(data: dict) -> bool:
    if not data:
        return False
    if data.get('is_active') is False:
        return True
    status = (data.get('status') or '').lower()
    return status in ('suspenso', 'suspended', 'inativo', 'inactive')


def _apply_local_block(local_provedor, reason: str) -> None:
    update_fields = []
    if local_provedor.is_active:
        local_provedor.is_active = False
        update_fields.append('is_active')
    reason = (reason or _DEFAULT_BLOCK_MESSAGE).strip()
    if (local_provedor.block_reason or '').strip() != reason:
        local_provedor.block_reason = reason
        update_fields.append('block_reason')
    if update_fields:
        update_fields.append('updated_at')
        local_provedor.save(update_fields=update_fields)


def _fetch_central_block_state(central_id: int, *, use_cache: bool) -> Tuple[bool, str]:
    now = time.monotonic()
    if use_cache:
        cached = _CENTRAL_SYNC_CACHE.get(central_id)
        if cached and (now - cached[0]) < _CENTRAL_SYNC_TTL_SEC:
            return cached[1], cached[2]

    from integrations.superadmin_notifier import fetch_central_provedor_by_id

    data = fetch_central_provedor_by_id(central_id)
    blocked = _central_is_blocked(data or {})
    reason = _reason_from_central(data or {}) if blocked else ''
    _CENTRAL_SYNC_CACHE[central_id] = (now, blocked, reason)
    return blocked, reason


def refresh_provedores_block_from_superadmin(
    provedores: List,
    *,
    use_cache: bool = False,
) -> None:
    """
    Espelha is_active do superadmin no tenant (webhook atrasado ou id local ≠ central).
    """
    if not provedores:
        return

    sync_key = tuple(sorted(p.id for p in provedores))
    now = time.monotonic()
    if use_cache and now - _LAST_SYNC_AT.get(sync_key, 0.0) < _CENTRAL_SYNC_TTL_SEC:
        return
    _LAST_SYNC_AT[sync_key] = now

    from integrations.superadmin_notifier import (
        fetch_central_provedor_by_id,
        fetch_central_provedor_by_subdomain,
        fetch_superadmin_tenant_billing_status,
    )

    # 1) Bearer integration_token (não depende de ADMIN_WEBHOOK_SECRET)
    try:
        central = fetch_superadmin_tenant_billing_status()
        if isinstance(central, dict) and central.get('blocked'):
            reason = (central.get('reason') or '').strip() or _DEFAULT_BLOCK_MESSAGE
            for provedor in provedores:
                _apply_local_block(provedor, reason)
            return
        if isinstance(central, dict) and central.get('blocked') is False:
            for provedor in provedores:
                if not provedor.is_active:
                    provedor.is_active = True
                    provedor.block_reason = ''
                    provedor.save(update_fields=['is_active', 'block_reason', 'updated_at'])
            return
    except Exception as exc:
        logger.warning('[login] sync tenant-billing-status: %s', exc)

    # 2) Lookup por subdomínio ou id central (ADMIN_WEBHOOK_SECRET)
    central_data = fetch_central_provedor_by_subdomain()
    if not central_data:
        central_id = resolve_central_provedor_id()
        if central_id:
            try:
                blocked, reason = _fetch_central_block_state(central_id, use_cache=use_cache)
                if blocked:
                    for provedor in provedores:
                        _apply_local_block(provedor, reason)
                elif not blocked:
                    for provedor in provedores:
                        if not provedor.is_active:
                            provedor.is_active = True
                            provedor.block_reason = ''
                            provedor.save(update_fields=['is_active', 'block_reason', 'updated_at'])
            except Exception as exc:
                logger.warning('[login] sync central lookup id=%s: %s', central_id, exc)
        return

    if _central_is_blocked(central_data):
        reason = _reason_from_central(central_data)
        for provedor in provedores:
            _apply_local_block(provedor, reason)
        return

    if central_data.get('is_active') is True:
        for provedor in provedores:
            if not provedor.is_active:
                provedor.is_active = True
                provedor.block_reason = ''
                provedor.save(update_fields=['is_active', 'block_reason', 'updated_at'])


def _inactive_provedor_message(provedores: List) -> Optional[str]:
    for provedor in provedores:
        if not provedor.is_active:
            reason = (provedor.block_reason or '').strip()
            return reason or _DEFAULT_BLOCK_MESSAGE
    return None


def login_denied_message_for_user(user, *, sync_central: bool = True) -> Optional[str]:
    """
    Retorna mensagem de erro se o login deve ser negado; None se permitido.
    """
    if getattr(user, 'user_type', None) == 'superadmin':
        return None

    provedores = collect_user_provedores(user)
    if not provedores:
        return None

    if sync_central:
        refresh_provedores_block_from_superadmin(provedores, use_cache=False)
        for provedor in provedores:
            provedor.refresh_from_db(fields=['is_active', 'block_reason'])

    return _inactive_provedor_message(provedores)


def api_access_denied_message_for_user(user) -> Optional[str]:
    """Requests autenticados: sync central com cache curto."""
    if getattr(user, 'user_type', None) == 'superadmin':
        return None

    provedores = collect_user_provedores(user)
    if not provedores:
        return None

    refresh_provedores_block_from_superadmin(provedores, use_cache=True)
    for provedor in provedores:
        provedor.refresh_from_db(fields=['is_active', 'block_reason'])

    return _inactive_provedor_message(provedores)


def user_provedor_payment_blocked(user) -> Tuple[bool, Optional[str]]:
    """
    Usado por status_pagamento / BlockedScreen: (blocked, reason).
    """
    if getattr(user, 'user_type', None) == 'superadmin':
        return False, None

    provedores = collect_user_provedores(user)
    if not provedores:
        return False, None

    refresh_provedores_block_from_superadmin(provedores, use_cache=True)
    for provedor in provedores:
        provedor.refresh_from_db(fields=['is_active', 'block_reason'])

    msg = _inactive_provedor_message(provedores)
    return (msg is not None, msg)
