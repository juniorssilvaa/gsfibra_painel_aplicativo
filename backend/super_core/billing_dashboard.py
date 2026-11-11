"""
Agrega dados de cobrança de provedores para o dashboard do Superadmin:
- vencimento próximo (até 3 dias)
- valor a receber (soma das assinaturas Asaas)
- mensagens de cobrança enviadas (WhatsApp)
- títulos/recibos recebidos no Asaas
"""
from __future__ import annotations

import logging
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any

from django.db.models import Q
from django.utils import timezone

from integrations.asaas_config import get_asaas_access_token
from integrations.asaas_entity import asaas_subscription_is_active
from integrations.asaas_service import AsaasService

from .models import BillingSendLog, Provedor

logger = logging.getLogger(__name__)

# Janela "perto do vencimento": hoje até +N dias (inclusivo)
DUE_SOON_DAYS = 3


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


def _money(value) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        y, m, d = [int(x) for x in str(raw).split('-')[:3]]
        return date(y, m, d)
    except Exception:
        return None


def _fetch_payments_due_soon(
    asaas: AsaasService,
    start: date,
    end: date,
) -> tuple[list[dict], str | None]:
    """PENDING + OVERDUE com vencimento entre start e end (confirma itens ativos)."""
    start_s = start.isoformat()
    end_s = end.isoformat()
    all_items: list[dict] = []
    err: str | None = None

    for status in ('PENDING', 'OVERDUE'):
        offset = 0
        limit = 100
        while True:
            res = asaas.list_payments(
                status=status,
                due_date_ge=start_s,
                due_date_le=end_s,
                offset=offset,
                limit=limit,
            )
            if not res.get('success'):
                err = res.get('error') or f'Falha ao listar {status}'
                break
            raw = res.get('data') or []
            if not raw:
                break
            all_items.extend(asaas.confirm_payments(raw, max_items=limit))
            if len(raw) < limit:
                break
            offset += limit

    by_id: dict[str, dict] = {}
    for p in all_items:
        pid = str(p.get('id') or '')
        if pid:
            by_id[pid] = p
    return list(by_id.values()), err


def _fetch_all_subscriptions(asaas: AsaasService) -> tuple[list[dict], str | None]:
    """Todas as assinaturas ativas no Asaas (paginado)."""
    all_items: list[dict] = []
    err: str | None = None
    offset = 0
    limit = 100
    while True:
        res = asaas.list_subscriptions(offset=offset, limit=limit)
        if not res.get('success'):
            err = res.get('error') or 'Falha ao listar assinaturas'
            break
        raw = res.get('data') or []
        if not raw:
            break
        for sub in raw:
            if asaas_subscription_is_active(sub):
                all_items.append(sub)
        if len(raw) < limit:
            break
        offset += limit
    return all_items, err


def _fetch_received_month(asaas: AsaasService, year: int, month: int) -> tuple[list[dict], str | None]:
    first = date(year, month, 1)
    last = date(year, month, monthrange(year, month)[1])
    all_items: list[dict] = []
    err: str | None = None

    for status in ('RECEIVED', 'CONFIRMED'):
        offset = 0
        limit = 100
        while True:
            res = asaas.list_payments(
                status=status,
                payment_date_ge=first.isoformat(),
                payment_date_le=last.isoformat(),
                offset=offset,
                limit=limit,
            )
            if not res.get('success'):
                err = res.get('error') or f'Falha ao listar {status}'
                break
            raw = res.get('data') or []
            if not raw:
                break
            all_items.extend(raw)
            if len(raw) < limit:
                break
            offset += limit

    by_id: dict[str, dict] = {}
    for p in all_items:
        pid = str(p.get('id') or '')
        if pid:
            by_id[pid] = p
    return list(by_id.values()), err


def _match_provedores(
    payments: list[dict],
    by_sub: dict[str, Provedor],
    by_cust: dict[str, Provedor],
) -> list[dict]:
    items: list[dict] = []
    seen: set[int] = set()

    for payment in payments:
        sub_id = _payment_subscription_id(payment)
        cust_id = _payment_customer_id(payment)
        prov = by_sub.get(sub_id) if sub_id else None
        if not prov and cust_id:
            prov = by_cust.get(cust_id)
        if not prov or prov.id in seen:
            continue
        seen.add(prov.id)
        due = payment.get('dueDate')
        due_d = _parse_iso_date(due)
        days_until = (due_d - timezone.localdate()).days if due_d else None
        items.append({
            'id': prov.id,
            'nome': prov.nome,
            'subdomain': (prov.subdomain or '').strip(),
            'is_active': prov.is_active,
            'subscription_status': prov.subscription_status or '',
            'subscription_next_due_date': (
                prov.subscription_next_due_date.isoformat()
                if prov.subscription_next_due_date else None
            ),
            'days_until_due': days_until,
            'payment': {
                'id': payment.get('id'),
                'dueDate': due,
                'value': _money(payment.get('value')),
                'status': payment.get('status') or '',
                'invoiceUrl': payment.get('invoiceUrl') or payment.get('bankSlipUrl') or '',
                'description': (payment.get('description') or '').strip(),
            },
            'source': 'asaas',
        })
    return items


def get_billing_overview() -> dict[str, Any]:
    today = timezone.localdate()
    due_until = today + timedelta(days=DUE_SOON_DAYS)
    now = timezone.localtime()
    day_start = timezone.make_aware(datetime.combine(today, time.min))
    day_end = day_start + timedelta(days=1)

    token_ok = bool(get_asaas_access_token())
    asaas_error: str | None = None

    provedores_qs = list(
        Provedor.objects.filter(
            Q(asaas_subscription_id__isnull=False) & ~Q(asaas_subscription_id='')
            | Q(asaas_customer_id__isnull=False) & ~Q(asaas_customer_id='')
            | Q(subscription_next_due_date__gte=today, subscription_next_due_date__lte=due_until)
        ).only(
            'id', 'nome', 'subdomain', 'is_active', 'subscription_status',
            'subscription_next_due_date', 'subscription_value',
            'asaas_subscription_id', 'asaas_customer_id',
        )
    )
    by_sub: dict[str, Provedor] = {}
    by_cust: dict[str, Provedor] = {}
    for p in provedores_qs:
        sid = (p.asaas_subscription_id or '').strip()
        cid = (p.asaas_customer_id or '').strip()
        if sid:
            by_sub[sid] = p
        if cid:
            by_cust[cid] = p

    due_soon_items: list[dict] = []
    due_soon_value = 0.0
    subscriptions_receivable = {
        'total_value': 0.0,
        'total_count': 0,
        'source': 'none',
    }

    if token_ok:
        asaas = AsaasService()
        due_payments, due_err = _fetch_payments_due_soon(asaas, today, due_until)
        if due_err:
            asaas_error = due_err
        due_soon_items = _match_provedores(due_payments, by_sub, by_cust)

        subs, subs_err = _fetch_all_subscriptions(asaas)
        if subs_err and not asaas_error:
            asaas_error = subs_err
        if not subs_err:
            total_sub_value = sum(_money(s.get('value')) for s in subs)
            subscriptions_receivable = {
                'total_value': round(total_sub_value, 2),
                'total_count': len(subs),
                'source': 'asaas',
            }
    else:
        asaas = None

    if subscriptions_receivable['source'] != 'asaas':
        local_subs = list(
            Provedor.objects.filter(
                Q(asaas_subscription_id__isnull=False) & ~Q(asaas_subscription_id='')
            ).only('subscription_value', 'asaas_subscription_id')
        )
        subscriptions_receivable = {
            'total_value': round(sum(_money(p.subscription_value) for p in local_subs), 2),
            'total_count': len(local_subs),
            'source': 'local',
        }

    seen_ids = {x['id'] for x in due_soon_items}
    for prov in provedores_qs:
        if prov.id in seen_ids:
            continue
        local_due = prov.subscription_next_due_date
        if not local_due or local_due < today or local_due > due_until:
            continue
        days_until = (local_due - today).days
        due_soon_items.append({
            'id': prov.id,
            'nome': prov.nome,
            'subdomain': (prov.subdomain or '').strip(),
            'is_active': prov.is_active,
            'subscription_status': prov.subscription_status or '',
            'subscription_next_due_date': local_due.isoformat(),
            'days_until_due': days_until,
            'payment': {
                'id': None,
                'dueDate': local_due.isoformat(),
                'value': _money(prov.subscription_value),
                'status': prov.subscription_status or '',
                'invoiceUrl': '',
                'description': 'Vencimento local (subscription_next_due_date)',
            },
            'source': 'local',
        })

    due_soon_items.sort(
        key=lambda x: (
            x.get('days_until_due') if x.get('days_until_due') is not None else 999,
            (x.get('nome') or '').lower(),
        ),
    )
    due_soon_value = sum(
        (x.get('payment') or {}).get('value') or 0 for x in due_soon_items
    )

    logs_today = BillingSendLog.objects.filter(
        created_at__gte=day_start,
        created_at__lt=day_end,
    )
    sent_ok = logs_today.filter(success=True).count()
    sent_err = logs_today.filter(success=False).count()
    messages_items = []
    for log in logs_today.select_related('provedor').order_by('-created_at')[:40]:
        messages_items.append({
            'id': log.id,
            'provedor_id': log.provedor_id,
            'provedor_nome': log.provedor.nome if log.provedor else None,
            'phone': log.phone,
            'template_name': log.template_name,
            'due_offset': log.due_offset,
            'due_date': log.due_date.isoformat() if log.due_date else None,
            'value': _money(log.value),
            'success': log.success,
            'error_message': (log.error_message or '')[:200],
            'created_at': log.created_at.isoformat() if log.created_at else None,
        })

    received_items_raw: list[dict] = []
    received_error: str | None = None
    daily: dict[str, dict[str, float | int]] = defaultdict(lambda: {'value': 0.0, 'count': 0})

    if token_ok and asaas is not None:
        received_items_raw, received_error = _fetch_received_month(asaas, today.year, today.month)
        if received_error and not asaas_error:
            asaas_error = received_error

    received_matched = []
    for payment in received_items_raw:
        sub_id = _payment_subscription_id(payment)
        cust_id = _payment_customer_id(payment)
        prov = by_sub.get(sub_id) if sub_id else None
        if not prov and cust_id:
            prov = by_cust.get(cust_id)
        if not prov:
            continue

        pay_day = _parse_iso_date(payment.get('paymentDate') or payment.get('confirmedDate'))
        if not pay_day or pay_day.year != today.year or pay_day.month != today.month:
            continue
        val = _money(payment.get('value'))
        key = pay_day.isoformat()
        daily[key]['value'] = round(float(daily[key]['value']) + val, 2)
        daily[key]['count'] = int(daily[key]['count']) + 1
        received_matched.append({
            'id': payment.get('id'),
            'provedor_id': prov.id,
            'provedor_nome': prov.nome,
            'value': val,
            'paymentDate': pay_day.isoformat(),
            'dueDate': payment.get('dueDate'),
            'status': payment.get('status') or '',
            'invoiceUrl': payment.get('invoiceUrl') or '',
            'description': (payment.get('description') or '').strip(),
        })

    days_in_month = monthrange(today.year, today.month)[1]
    chart_days = []
    for d in range(1, days_in_month + 1):
        key = date(today.year, today.month, d).isoformat()
        chart_days.append({
            'date': key,
            'label': f'{d}/{today.month}',
            'value': float(daily[key]['value']) if key in daily else 0.0,
            'count': int(daily[key]['count']) if key in daily else 0,
        })

    total_received_value = sum(x['value'] for x in received_matched)
    total_received_count = len(received_matched)
    received_today = [
        x for x in received_matched
        if x.get('paymentDate') == today.isoformat()
    ]

    due_payload = {
        'total': len(due_soon_items),
        'total_value': round(due_soon_value, 2),
        'days_window': DUE_SOON_DAYS,
        'until': due_until.isoformat(),
        'items': due_soon_items,
    }

    return {
        'success': True,
        'asaas_configured': token_ok,
        'error': asaas_error,
        'today': today.isoformat(),
        'generated_at': now.isoformat(),
        'due_soon': due_payload,
        'due_today': due_payload,
        'subscriptions_receivable': subscriptions_receivable,
        'billing_messages': {
            'sent_ok': sent_ok,
            'sent_err': sent_err,
            'total': sent_ok + sent_err,
            'items': messages_items,
        },
        'titles_received': {
            'month': f'{today.year}-{today.month:02d}',
            'total_value': round(total_received_value, 2),
            'total_count': total_received_count,
            'today_count': len(received_today),
            'today_value': round(sum(x['value'] for x in received_today), 2),
            'chart': chart_days,
            'recent': sorted(
                received_matched,
                key=lambda x: x.get('paymentDate') or '',
                reverse=True,
            )[:25],
        },
    }
