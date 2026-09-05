"""Provisionamento e bloqueio do ACS junto com os demais serviços do provedor."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from .models import AcsLicense, AcsProfile

logger = logging.getLogger(__name__)


@transaction.atomic
def ensure_acs_for_provedor(
    provedor,
    *,
    is_active=True,
    create_license=True,
    expiration_date=None,
    max_onts=100,
):
    """
    Garante AcsProfile (+ licença ativa) para o provedor.
    Idempotente.
    """
    profile, created = AcsProfile.objects.get_or_create(
        provedor=provedor,
        defaults={'is_active': is_active},
    )
    if not created and profile.is_active != is_active:
        profile.is_active = is_active
        profile.save(update_fields=['is_active', 'updated_at'])

    license_obj = profile.licenses.order_by('-created_at').first()
    if create_license and not license_obj:
        exp = expiration_date
        if isinstance(exp, str) and exp.strip():
            from datetime import date as date_cls
            exp = date_cls.fromisoformat(exp.strip()[:10])
        exp = exp or (date.today() + timedelta(days=365))
        license_obj = AcsLicense.objects.create(
            profile=profile,
            expiration_date=exp,
            max_onts=int(max_onts or 100),
            status='active' if is_active else 'suspended',
            suspend_source='' if is_active else 'manual',
        )
    elif license_obj and not is_active and license_obj.status == 'active':
        license_obj.status = 'suspended'
        license_obj.suspend_source = 'manual'
        license_obj.save(update_fields=['status', 'suspend_source'])
    elif license_obj and is_active and license_obj.status == 'suspended' and license_obj.suspend_source == 'manual':
        today = timezone.localdate()
        if license_obj.expiration_date and license_obj.expiration_date < today:
            license_obj.status = 'expired'
            license_obj.suspend_source = ''
        else:
            license_obj.status = 'active'
            license_obj.suspend_source = ''
        license_obj.save(update_fields=['status', 'suspend_source'])

    return profile, license_obj, created


def sync_acs_access(provedor, active: bool, *, source='billing') -> None:
    """
    Espelha o bloqueio/desbloqueio do provedor nas licenças ACS.
    source=billing: suspensão automática (fatura / is_active do provedor).
    """
    try:
        profile = AcsProfile.objects.filter(provedor_id=provedor.id).first()
        if not profile:
            return
        if profile.is_active != bool(active):
            profile.is_active = bool(active)
            profile.save(update_fields=['is_active', 'updated_at'])

        today = timezone.localdate()
        licenses = list(profile.licenses.all())
        for lic in licenses:
            if not active:
                if lic.status == 'active':
                    lic.status = 'suspended'
                    lic.suspend_source = source
                    lic.save(update_fields=['status', 'suspend_source'])
                continue

            if lic.status == 'suspended' and lic.suspend_source in (source, 'billing'):
                if lic.expiration_date and lic.expiration_date < today:
                    lic.status = 'expired'
                    lic.suspend_source = ''
                else:
                    lic.status = 'active'
                    lic.suspend_source = ''
                lic.save(update_fields=['status', 'suspend_source'])
            elif lic.status == 'active' and lic.expiration_date and lic.expiration_date < today:
                lic.status = 'expired'
                lic.save(update_fields=['status'])
    except Exception as exc:
        logger.warning('[acs] Falha ao sincronizar acesso provedor=%s: %s', getattr(provedor, 'id', None), exc)
