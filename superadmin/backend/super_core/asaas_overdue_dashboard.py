"""
Agrega provedores com cobrança OVERDUE no Asaas para o dashboard do superadmin.
"""
from __future__ import annotations

import logging
from typing import Any

from django.db.models import Q

from integrations.asaas_config import get_asaas_access_token
from integrations.asaas_service import AsaasService

from django.utils import timezone

from .models import Provedor

logger = logging.getLogger(__name__)


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


def _payment_subscription_id(payment: dict) -> str:
    sub = payment.get('subscription')
    if isinstance(sub, dict):
        return str(sub.get('id') or '').strip()
    return str(sub or '').strip()


def _payment_customer_id(payment: dict) -> str:
    cust = payment.get('customer')
    if isinstance(cust, dict):
        return str(cust.get('id') or '').strip()
    return str(cust or '').strip()


def _fetch_all_overdue_payments() -> tuple[list[dict], str | None]:
    asaas = AsaasService()
    if not asaas.access_token:
        return [], 'asaas_access_token não configurado'

    all_items: list[dict] = []
    offset = 0
    limit = 100
    while True:
        res = asaas.list_payments(status='OVERDUE', offset=offset, limit=limit)
        if not res.get('success'):
            return all_items, res.get('error') or 'Falha ao consultar Asaas'
        raw = res.get('data') or []
        if not raw:
            break
        chunk = asaas.confirm_payments(raw, max_items=limit)
        all_items.extend(chunk)
        if len(raw) < limit:
            break
        offset += limit
    return all_items, None


def _index_overdue_payments(payments: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    """Por assinatura e por cliente: fica a cobrança mais antiga (maior atraso)."""
    by_sub: dict[str, dict] = {}
    by_customer: dict[str, dict] = {}

    def _should_replace(current: dict | None, candidate: dict) -> bool:
        if not current:
            return True
        cur_due = current.get('dueDate') or '9999-99-99'
        new_due = candidate.get('dueDate') or '9999-99-99'
        return new_due < cur_due

    for payment in payments:
        sub_id = _payment_subscription_id(payment)
        cust_id = _payment_customer_id(payment)
        if sub_id and _should_replace(by_sub.get(sub_id), payment):
            by_sub[sub_id] = payment
        if cust_id and _should_replace(by_customer.get(cust_id), payment):
            by_customer[cust_id] = payment

    return by_sub, by_customer


def _serialize_payment(payment: dict | None) -> dict | None:
    if not payment:
        return None
    due = payment.get('dueDate')
    value = payment.get('value')
    try:
        value_f = float(value) if value is not None else None
    except (TypeError, ValueError):
        value_f = None
    return {
        'id': payment.get('id'),
        'description': (payment.get('description') or '').strip(),
        'dueDate': due,
        'value': value_f,
        'days_late': _compute_days_late(due),
        'invoiceUrl': payment.get('invoiceUrl') or payment.get('bankSlipUrl') or '',
        'status': payment.get('status') or 'OVERDUE',
    }


def get_provedores_asaas_overdue() -> dict[str, Any]:
    token_ok = bool(get_asaas_access_token())
    if not token_ok:
        return {
            'success': False,
            'asaas_configured': False,
            'error': 'Token do Asaas não configurado',
            'total': 0,
            'items': [],
        }

    payments, fetch_error = _fetch_all_overdue_payments()
    by_sub, by_customer = _index_overdue_payments(payments)

    provedores_qs = Provedor.objects.filter(
        Q(asaas_subscription_id__isnull=False) & ~Q(asaas_subscription_id='')
        | Q(asaas_customer_id__isnull=False) & ~Q(asaas_customer_id='')
        | Q(subscription_status__iexact='OVERDUE')
    ).only(
        'id', 'nome', 'subdomain', 'is_active', 'status', 'subscription_status',
        'asaas_subscription_id', 'asaas_customer_id',
    )

    items: list[dict] = []
    seen_ids: set[int] = set()

    for prov in provedores_qs:
        sub_id = (prov.asaas_subscription_id or '').strip()
        cust_id = (prov.asaas_customer_id or '').strip()
        payment = None
        if sub_id:
            payment = by_sub.get(sub_id)
        if not payment and cust_id:
            payment = by_customer.get(cust_id)

        local_overdue = (prov.subscription_status or '').upper() == 'OVERDUE'
        if not payment and not local_overdue:
            continue

        seen_ids.add(prov.id)
        payment_data = _serialize_payment(payment)
        days_late = (payment_data or {}).get('days_late') or 0
        items.append({
            'id': prov.id,
            'nome': prov.nome,
            'subdomain': (prov.subdomain or '').strip(),
            'is_active': prov.is_active,
            'status': prov.status,
            'subscription_status': prov.subscription_status or '',
            'payment': payment_data,
            'days_late': days_late,
            'source': 'asaas' if payment else 'local_status',
        })

    items.sort(
        key=lambda x: (
            -(x.get('days_late') or 0),
            (x.get('nome') or '').lower(),
        ),
    )

    total_value = sum(
        (x.get('payment') or {}).get('value') or 0
        for x in items
        if (x.get('payment') or {}).get('value')
    )

    return {
        'success': fetch_error is None,
        'asaas_configured': True,
        'error': fetch_error,
        'total': len(items),
        'total_value': round(total_value, 2),
        'items': items,
    }
