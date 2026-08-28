"""
Bloqueio automático de provedores por cobrança OVERDUE da assinatura no Asaas.
Configurável em SystemConfig (superadmin).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone

from core.models import Provedor, SystemConfig
from integrations.asaas_service import AsaasService

logger = logging.getLogger(__name__)


def _parse_due_date(due_date_str: Optional[str]):
    if not due_date_str:
        return None
    try:
        return datetime.strptime(str(due_date_str)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def payment_is_blocking_overdue(
    due_date_str: Optional[str], min_days_late: int
) -> bool:
    """
    True quando já se passaram pelo menos `min_days_late` dias inteiros desde o vencimento.
    min_days_late=0: qualquer dia igual ou posterior ao vencimento (fatura já vencida no calendário).
    min_days_late=1: pelo menos um dia após o vencimento.
    min_days_late=4: compatível com a regra antiga do sistema (antes era "mais de 3 dias" de atraso).
    """
    due = _parse_due_date(due_date_str)
    if not due:
        return False
    delta = (timezone.now().date() - due).days
    return delta >= int(min_days_late)


def is_asaas_auto_inadimplencia_reason(reason: Optional[str]) -> bool:
    if not reason:
        return False
    r = reason.lower()
    return "asaas" in r and "inadimpl" in r


def get_auto_block_settings() -> Tuple[bool, int]:
    """(ligado, dias_mínimos_após_vencimento_para_bloquear)"""
    config = SystemConfig.objects.filter(key="system_config").first() or SystemConfig.objects.first()
    if not config:
        return True, 4
    enabled = bool(getattr(config, "billing_provedor_auto_block_enabled", True))
    try:
        min_late = int(getattr(config, "billing_provedor_block_min_days_late", None))
    except (TypeError, ValueError):
        min_late = 4
    min_late = max(0, min(min_late, 365))
    return enabled, min_late


def block_reason_text(min_days_late: int) -> str:
    n = int(min_days_late)
    if n <= 0:
        return "Bloqueado por inadimplência Asaas (fatura em atraso)."
    return f"Bloqueado por inadimplência Asaas (fatura vencida há {n} dia(s) ou mais)."


def list_subscription_overdue_payments(
    provedor: Provedor, asaas_service: AsaasService
) -> Tuple[bool, List[Dict[str, Any]], str]:
    """(ok, lista de pagamentos OVERDUE, mensagem_erro)"""
    if not provedor.asaas_customer_id:
        return True, [], ""
    if provedor.asaas_subscription_id:
        res = asaas_service.list_payments(
            subscription_id=provedor.asaas_subscription_id,
            status="OVERDUE",
        )
    else:
        res = asaas_service.list_payments(
            customer=provedor.asaas_customer_id,
            status="OVERDUE",
        )
    if not res.get("success"):
        return False, [], str(res.get("error") or "erro Asaas")
    data = res.get("data") or []
    data.sort(key=lambda x: x.get("dueDate", "") or "")
    return True, data, ""


def apply_subscription_overdue_block_for_provedor(
    provedor: Provedor,
    asaas_service: Optional[AsaasService] = None,
) -> Dict[str, Any]:
    """
    Atualiza is_active / block_reason conforme inadimplência da assinatura no Asaas.
    Retorna {"changes": bool, "billing": str}.
    """
    enabled, min_days_late = get_auto_block_settings()
    asaas_service = asaas_service or AsaasService()
    changes = False

    if not enabled:
        if (
            (not provedor.is_active)
            and provedor.block_reason
            and is_asaas_auto_inadimplencia_reason(provedor.block_reason)
        ):
            provedor.is_active = True
            provedor.block_reason = None
            changes = True
            return {"changes": changes, "billing": "auto_block_disabled_cleared"}

        return {"changes": False, "billing": "auto_block_disabled"}

    if not provedor.asaas_customer_id or not provedor.asaas_subscription_id:
        return {"changes": False, "billing": "skipped_no_subscription"}

    overdue_res = asaas_service.list_payments(
        subscription_id=provedor.asaas_subscription_id,
        status="OVERDUE",
    )
    if not overdue_res.get("success"):
        return {
            "changes": False,
            "billing": f"error: {overdue_res.get('error')}",
        }

    overdue_payments: List[Dict[str, Any]] = overdue_res.get("data", []) or []
    eligible = [
        p
        for p in overdue_payments
        if payment_is_blocking_overdue(p.get("dueDate"), min_days_late)
    ]
    has_blocking = len(eligible) > 0

    if has_blocking:
        reason = block_reason_text(min_days_late)
        if provedor.is_active or provedor.block_reason != reason:
            provedor.is_active = False
            provedor.block_reason = reason
            changes = True
        return {"changes": changes, "billing": f"overdue_block_min{min_days_late}d"}
    if (
        (not provedor.is_active)
        and provedor.block_reason
        and is_asaas_auto_inadimplencia_reason(provedor.block_reason)
    ):
        provedor.is_active = True
        provedor.block_reason = None
        changes = True
    billing = "overdue_grace" if overdue_payments else "ok"
    return {"changes": changes, "billing": billing}


def run_periodic_asaas_provedor_blocks() -> Dict[str, Any]:
    """Varre provedores com assinatura Asaas e aplica bloqueio/desbloqueio."""
    enabled, _ = get_auto_block_settings()
    if not enabled:
        return {"skipped": True, "reason": "auto_block_disabled"}

    asaas = AsaasService()
    if not asaas.access_token:
        return {"skipped": True, "reason": "no_asaas_token"}

    updated = 0
    errors = 0
    qs = (
        Provedor.objects.exclude(asaas_subscription_id__isnull=True)
        .exclude(asaas_subscription_id="")
        .iterator(chunk_size=50)
    )
    for provedor in qs:
        try:
            res = apply_subscription_overdue_block_for_provedor(provedor, asaas)
            if res.get("changes"):
                provedor.save(update_fields=["is_active", "block_reason", "updated_at"])
                updated += 1
        except Exception:
            errors += 1
            logger.exception(
                "[AsaasAutoBlock] falha provedor id=%s", getattr(provedor, "id", None)
            )

    if updated or errors:
        logger.info(
            "[AsaasAutoBlock] ciclo concluído | atualizados=%s erros=%s",
            updated,
            errors,
        )
    return {"updated": updated, "errors": errors, "enabled": True}
