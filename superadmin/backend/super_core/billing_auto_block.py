"""
Bloqueio automático de provedores por fatura OVERDUE no Asaas (config no SystemConfig).
"""
from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

from integrations.asaas_service import AsaasService

from .models import Provedor, SystemConfig

logger = logging.getLogger(__name__)


def get_auto_block_settings() -> tuple[bool, int]:
    config = SystemConfig.objects.first()
    payload = (config.payload or {}) if config else {}
    enabled = bool(payload.get('billing_provedor_auto_block_enabled', False))
    try:
        min_days = int(payload.get('billing_provedor_block_min_days_late', 4))
    except (TypeError, ValueError):
        min_days = 4
    return enabled, max(0, min(365, min_days))


def _compute_days_late(due_date_iso: str) -> int:
    if not due_date_iso:
        return 0
    try:
        from datetime import date
        y, m, d = [int(x) for x in str(due_date_iso).split('-')[:3]]
        due = date(y, m, d)
        return max(0, (timezone.localdate() - due).days)
    except Exception:
        return 0


def _block_reason_text(days_late: int, min_days: int) -> str:
    return (
        f'Acesso suspenso: fatura vencida há {days_late} dia(s) '
        f'(limite: {min_days} dia(s) após o vencimento). '
        'Regularize o pagamento para reativar o acesso.'
    )


def _provider_has_blocking_overdue(prov: Provedor, asaas: AsaasService, min_days: int) -> bool:
    """True se existe cobrança OVERDUE ativa além do prazo (Asaas ou Inter)."""
    is_inter = (
        (prov.billing_provider or '') == Provedor.BILLING_PROVIDER_INTER
        or (prov.asaas_subscription_id or '').startswith('INTER-SUB-')
    )
    if is_inter:
        from .models import InterBillingCharge

        for ch in InterBillingCharge.objects.filter(
            provedor=prov,
            status__in=[InterBillingCharge.STATUS_OVERDUE, InterBillingCharge.STATUS_PENDING],
        ).order_by('data_vencimento')[:10]:
            due = ch.data_vencimento.isoformat() if ch.data_vencimento else ''
            # PENDING só bloqueia se já passou do vencimento
            if ch.status == InterBillingCharge.STATUS_PENDING and _compute_days_late(due) <= 0:
                continue
            if _compute_days_late(due) >= min_days:
                return True
        return (prov.subscription_status or '').upper() == 'OVERDUE'

    sub_id = (prov.asaas_subscription_id or '').strip()
    if not sub_id:
        return (prov.subscription_status or '').upper() == 'OVERDUE'
    res = asaas.list_payments(subscription_id=sub_id, status='OVERDUE', limit=10)
    if not res.get('success'):
        return True
    for payment in asaas.confirm_payments(res.get('data') or [], max_items=10):
        if _compute_days_late(payment.get('dueDate')) >= min_days:
            return True
    return False


def sync_provedor_billing_block(prov: Provedor, *, asaas: AsaasService | None = None) -> dict[str, Any]:
    """
    Sincroniza bloqueio/desbloqueio de um provedor (Asaas ou Inter).
    """
    from django.core.cache import cache
    from .views import notify_provider_panel

    enabled, min_days = get_auto_block_settings()
    if not enabled:
        return {'changed': False, 'action': 'auto_block_disabled'}

    is_inter = (
        (prov.billing_provider or '') == Provedor.BILLING_PROVIDER_INTER
        or (prov.asaas_subscription_id or '').startswith('INTER-SUB-')
    )
    asaas = asaas or AsaasService()
    if not is_inter and not asaas.access_token:
        return {'changed': False, 'action': 'no_asaas_token'}

    has_blocking = _provider_has_blocking_overdue(prov, asaas, min_days)

    if has_blocking:
        if not ((not prov.is_active) and prov.status == 'suspenso'):
            days_late = 0
            if is_inter:
                from .models import InterBillingCharge

                for ch in InterBillingCharge.objects.filter(
                    provedor=prov,
                    status__in=[InterBillingCharge.STATUS_OVERDUE, InterBillingCharge.STATUS_PENDING],
                )[:10]:
                    due = ch.data_vencimento.isoformat() if ch.data_vencimento else ''
                    days_late = max(days_late, _compute_days_late(due))
            else:
                sub_id = (prov.asaas_subscription_id or '').strip()
                if sub_id:
                    res = asaas.list_payments(subscription_id=sub_id, status='OVERDUE', limit=10)
                    if res.get('success'):
                        for payment in asaas.confirm_payments(res.get('data') or [], max_items=10):
                            days_late = max(days_late, _compute_days_late(payment.get('dueDate')))
            reason = _block_reason_text(days_late or min_days, min_days)
            prov.is_active = False
            prov.status = 'suspenso'
            prov.subscription_status = 'OVERDUE'
            prov.save(update_fields=['is_active', 'status', 'subscription_status'])
            try:
                from mobile_app.models import MobileAppProfile
                MobileAppProfile.objects.filter(provedor_id=prov.id).update(is_active=False)
            except Exception:
                pass
            try:
                from acs.services import sync_acs_access
                sync_acs_access(prov, False, source='billing')
            except Exception:
                pass
            try:
                notify_provider_panel(prov.id, False, 'suspenso', block_reason=reason)
                cache.delete(f'auto_block_tenant_sync:{prov.id}')
            except Exception as exc:
                logger.warning('[AutoBlock] block notify provedor=%s: %s', prov.id, exc)
            logger.info('[AutoBlock] Bloqueado provedor %s (%s) via sync', prov.id, prov.nome)
            return {'changed': True, 'action': 'blocked', 'provedor_id': prov.id}

        return {'changed': False, 'action': 'already_blocked', 'provedor_id': prov.id}

    if (not prov.is_active) and prov.status == 'suspenso':
        prov.is_active = True
        prov.status = 'ativo'
        if (prov.subscription_status or '').upper() == 'OVERDUE':
            prov.subscription_status = 'ACTIVE'
        prov.save(update_fields=['is_active', 'status', 'subscription_status'])
        try:
            from mobile_app.models import MobileAppProfile
            MobileAppProfile.objects.filter(provedor_id=prov.id).update(is_active=True)
        except Exception:
            pass
        try:
            from acs.services import sync_acs_access
            sync_acs_access(prov, True, source='billing')
        except Exception:
            pass
        try:
            notify_provider_panel(prov.id, True, 'ativo')
            cache.delete(f'auto_block_tenant_sync:{prov.id}')
        except Exception as exc:
            logger.warning('[AutoBlock] release notify provedor=%s: %s', prov.id, exc)
        logger.info('[AutoBlock] Reativado provedor %s (%s) — sem fatura OVERDUE ativa', prov.id, prov.nome)
        return {'changed': True, 'action': 'released', 'provedor_id': prov.id}

    return {'changed': False, 'action': 'ok', 'provedor_id': prov.id}


def _release_provedores_without_active_overdue(asaas: AsaasService, min_days: int) -> int:
    """Reativa provedores suspensos por Asaas quando a fatura em atraso foi quitada."""
    released = 0
    qs = Provedor.objects.filter(is_active=False, status='suspenso').only(
        'id', 'nome', 'subdomain', 'integration_token', 'subscription_status',
        'asaas_subscription_id', 'is_active', 'status',
    )
    for prov in qs.iterator():
        if _provider_has_blocking_overdue(prov, asaas, min_days):
            continue
        result = sync_provedor_billing_block(prov, asaas=asaas)
        if result.get('action') == 'released':
            released += 1
    return released


def run_billing_auto_block_cycle() -> dict[str, Any]:
    """
    Suspende/reativa provedores com fatura vencida (Asaas ou Inter).
    """
    enabled, min_days = get_auto_block_settings()
    if not enabled:
        return {'skipped': True, 'reason': 'auto_block_disabled'}

    asaas = AsaasService()
    blocked = 0
    released = 0
    checked = 0
    errors = 0

    qs = (
        Provedor.objects.exclude(asaas_subscription_id__isnull=True)
        .exclude(asaas_subscription_id='')
        .only(
            'id', 'nome', 'asaas_subscription_id', 'billing_provider',
            'is_active', 'status', 'subscription_status',
            'subdomain', 'integration_token',
        )
    )

    for prov in qs.iterator():
        checked += 1
        try:
            result = sync_provedor_billing_block(prov, asaas=asaas)
            if result.get('action') == 'blocked':
                blocked += 1
            elif result.get('action') == 'released':
                released += 1
        except Exception:
            errors += 1
            logger.exception('[AutoBlock] provedor=%s falhou', prov.id)

    return {
        'checked': checked,
        'blocked': blocked,
        'released': released,
        'errors': errors,
        'min_days': min_days,
    }


def _sync_existing_blocks_to_tenants(asaas: AsaasService | None = None, min_days: int = 0) -> int:
    """Reenvia webhook para tenants quando o central já suspendeu (throttle 1h por provedor)."""
    from django.core.cache import cache
    from .views import notify_provider_panel

    asaas = asaas or AsaasService()
    synced = 0
    qs = Provedor.objects.filter(is_active=False, status='suspenso').only(
        'id', 'nome', 'subdomain', 'integration_token', 'subscription_status',
        'asaas_subscription_id',
    )
    for prov in qs.iterator():
        if not _provider_has_blocking_overdue(prov, asaas, min_days):
            continue
        cache_key = f'auto_block_tenant_sync:{prov.id}'
        if cache.get(cache_key):
            continue
        try:
            notify_provider_panel(
                prov.id,
                False,
                'suspenso',
                block_reason=(
                    'Sua fatura está em atraso. '
                    'Efetue o pagamento para reativar o acesso ao painel.'
                ),
            )
            cache.set(cache_key, '1', timeout=3600)
            synced += 1
        except Exception as exc:
            logger.warning('[AutoBlock] sync tenant provedor=%s: %s', prov.id, exc)
    return synced
