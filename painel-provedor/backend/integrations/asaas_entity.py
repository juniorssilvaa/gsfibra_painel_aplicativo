"""
Helpers para detectar cliente/assinatura removidos ou excluídos no Asaas.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional


def _text_blob(status_code: Optional[int], body: Any, data: Optional[Dict[str, Any]] = None) -> str:
    parts = [str(status_code or ''), str(body or '').lower()]
    if isinstance(data, dict):
        parts.append(json.dumps(data, ensure_ascii=False).lower())
    return ' '.join(parts)


def asaas_entity_is_removed(
    status_code: Optional[int] = None,
    body: Any = None,
    data: Optional[Dict[str, Any]] = None,
) -> bool:
    if status_code == 404:
        return True
    blob = _text_blob(status_code, body, data)
    markers = (
        'excluído',
        'excluido',
        'cliente excluído',
        'foi excluído',
        'não pode ser atualizado',
        'nao pode ser atualizado',
        'not found',
        'não encontrad',
        'nao encontrad',
    )
    if any(m in blob for m in markers):
        return True
    if isinstance(data, dict) and data.get('deleted') is True:
        return True
    return False


def asaas_customer_is_active(data: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get('deleted') is True:
        return False
    return True


def asaas_payment_is_active(payment: Optional[Dict[str, Any]]) -> bool:
    """Cobrança ainda existe no Asaas (excluídas continuam na listagem com deleted=true)."""
    if not isinstance(payment, dict):
        return False
    if payment.get('deleted') is True:
        return False
    return True


def filter_active_asaas_payments(payments: list | None) -> list:
    return [p for p in (payments or []) if asaas_payment_is_active(p)]


def confirm_payments_on_asaas(
    payments: list | None,
    fetch_payment: Callable[[str], Optional[Dict[str, Any]]],
    *,
    max_items: int = 50,
) -> list:
    confirmed: list = []
    seen: set[str] = set()
    for p in (payments or [])[:max_items]:
        if not asaas_payment_is_active(p):
            continue
        pid = (p.get('id') or '').strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        try:
            live = fetch_payment(pid)
        except Exception:
            continue
        if live and asaas_payment_is_active(live):
            confirmed.append(live)
    return confirmed
