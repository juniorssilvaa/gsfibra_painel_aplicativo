"""
Assinaturas no Banco Inter: estado local no Provedor + emissão de cobranças.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from integrations.inter_service import InterService
from super_core.models import InterBillingCharge, Provedor

logger = logging.getLogger(__name__)


def _parse_date(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        y, m, d = [int(x) for x in str(value).split("-")[:3]]
        return date(y, m, d)
    except Exception:
        return None


def _add_months(d: date, months: int = 1) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def _seu_numero(provedor_id: int, due: date) -> str:
    # Máx. 15 chars na API Inter
    return f"P{provedor_id}{due.strftime('%y%m%d')}"[:15]


def create_inter_subscription(provedor: Provedor, payload: dict | None = None) -> dict[str, Any]:
    """
    Ativa assinatura local no Inter e emite a primeira cobrança.
    Body esperado: value, cycle, billingType, nextDueDate (+ dados do pagador opcionais).
    """
    payload = payload or {}
    inter = InterService()
    if not inter.is_ready():
        raise RuntimeError("Banco Inter não configurado (client_id, secret, certificado e chave).")

    value = payload.get("value") if payload.get("value") is not None else provedor.subscription_value
    cycle = (payload.get("cycle") or provedor.subscription_cycle or "MONTHLY").upper()
    billing_type = (payload.get("billingType") or provedor.subscription_billing_type or "BOLETO").upper()
    next_due = _parse_date(
        payload.get("nextDueDate")
        or (provedor.subscription_next_due_date.isoformat() if provedor.subscription_next_due_date else None)
    )
    if not next_due:
        raise RuntimeError("nextDueDate é obrigatório")
    if float(value or 0) < 2.5:
        raise RuntimeError("Valor mínimo da cobrança Inter é R$ 2,50")

    cpf = "".join(ch for ch in str(payload.get("cpf_cnpj") or provedor.cpf_cnpj or "") if ch.isdigit())
    if len(cpf) not in (11, 14):
        raise RuntimeError("CPF/CNPJ do provedor é obrigatório para emitir no Inter")

    charge = emitir_cobranca_para_provedor(
        provedor,
        valor=float(value),
        data_vencimento=next_due,
        incoming=payload,
        inter=inter,
    )

    with transaction.atomic():
        provedor.billing_provider = Provedor.BILLING_PROVIDER_INTER
        # Marcador local (compatível com filtros que checam asaas_subscription_id)
        provedor.asaas_subscription_id = f"INTER-SUB-{provedor.id}"
        provedor.subscription_value = Decimal(str(round(float(value), 2)))
        provedor.subscription_cycle = cycle
        provedor.subscription_billing_type = billing_type
        provedor.subscription_next_due_date = next_due
        provedor.subscription_status = "PENDING"
        provedor.save(
            update_fields=[
                "billing_provider",
                "asaas_subscription_id",
                "subscription_value",
                "subscription_cycle",
                "subscription_billing_type",
                "subscription_next_due_date",
                "subscription_status",
            ]
        )

    return {
        "success": True,
        "subscription_id": provedor.asaas_subscription_id,
        "billing_provider": "inter",
        "charge": {
            "codigo_solicitacao": charge.codigo_solicitacao,
            "seu_numero": charge.seu_numero,
            "status": charge.status,
            "dueDate": charge.data_vencimento.isoformat() if charge.data_vencimento else None,
            "value": float(charge.valor),
        },
    }


def emitir_cobranca_para_provedor(
    provedor: Provedor,
    *,
    valor: float,
    data_vencimento: date,
    incoming: dict | None = None,
    inter: InterService | None = None,
) -> InterBillingCharge:
    inter = inter or InterService()
    if not inter.is_ready():
        raise RuntimeError("Banco Inter não configurado")

    seu_numero = _seu_numero(provedor.id, data_vencimento)
    existing = InterBillingCharge.objects.filter(provedor=provedor, seu_numero=seu_numero).exclude(
        status=InterBillingCharge.STATUS_CANCELLED
    ).first()
    if existing:
        return existing

    pagador = InterService.build_pagador_from_provedor(provedor, incoming)
    res = inter.emitir_cobranca(
        seu_numero=seu_numero,
        valor_nominal=valor,
        data_vencimento=data_vencimento.isoformat(),
        pagador=pagador,
        mensagem_linhas=[
            f"NioHub — {provedor.nome}",
            f"Mensalidade {data_vencimento.strftime('%m/%Y')}",
        ],
    )
    if not res.get("success"):
        raise RuntimeError(InterService.format_api_error(res.get("error") or "Falha ao emitir cobrança no Inter"))

    data = res.get("data") or {}
    codigo = (data.get("codigoSolicitacao") or "").strip()
    if not codigo:
        raise RuntimeError("Inter não retornou codigoSolicitacao")

    # Consulta detalhes (pode ainda estar processando)
    detail = inter.consultar_cobranca(codigo)
    detail_data = detail.get("data") if detail.get("success") else {}
    normalized = InterService.normalize_cobranca_item(detail_data or data, codigo_solicitacao=codigo)

    charge = InterBillingCharge.objects.create(
        provedor=provedor,
        codigo_solicitacao=codigo,
        seu_numero=seu_numero,
        valor=Decimal(str(round(float(valor), 2))),
        data_vencimento=data_vencimento,
        situacao=normalized.get("situacao") or "",
        status=normalized.get("status") or InterBillingCharge.STATUS_PENDING,
        linha_digitavel=normalized.get("linhaDigitavel") or "",
        pix_copia_cola=normalized.get("pixCopiaECola") or "",
        payload=detail_data or data,
    )
    logger.info(
        "[InterBilling] Cobrança emitida provedor=%s codigo=%s venc=%s",
        provedor.id,
        codigo,
        data_vencimento,
    )
    return charge


def refresh_charge_from_inter(charge: InterBillingCharge, inter: InterService | None = None) -> InterBillingCharge:
    """Consulta a cobrança no Inter e atualiza status local (+ assinatura do provedor se paga)."""
    inter = inter or InterService()
    res = inter.consultar_cobranca(charge.codigo_solicitacao)
    if not res.get("success"):
        return charge
    data = res.get("data") or {}
    normalized = InterService.normalize_cobranca_item(data, codigo_solicitacao=charge.codigo_solicitacao)
    prev_status = charge.status
    new_status = normalized.get("status") or charge.status
    # Compat: API interna usa DELETED; model usa CANCELLED
    if new_status == "DELETED":
        new_status = InterBillingCharge.STATUS_CANCELLED
    charge.situacao = normalized.get("situacao") or charge.situacao
    charge.status = new_status
    if normalized.get("linhaDigitavel"):
        charge.linha_digitavel = normalized["linhaDigitavel"]
    if normalized.get("pixCopiaECola"):
        charge.pix_copia_cola = normalized["pixCopiaECola"]
    charge.payload = data
    charge.save(
        update_fields=[
            "situacao",
            "status",
            "linha_digitavel",
            "pix_copia_cola",
            "payload",
            "updated_at",
        ]
    )
    if charge.status != prev_status or charge.status == InterBillingCharge.STATUS_RECEIVED:
        _apply_charge_status_to_provedor(charge)
    return charge


def _apply_charge_status_to_provedor(charge: InterBillingCharge) -> None:
    """Espelha RECEIVED/OVERDUE da cobrança Inter na assinatura local do provedor."""
    prov = charge.provedor
    if charge.status == InterBillingCharge.STATUS_RECEIVED:
        if charge.data_vencimento:
            next_due = _add_months(charge.data_vencimento, 1)
            current = prov.subscription_next_due_date
            if (not current) or current <= charge.data_vencimento:
                prov.subscription_next_due_date = next_due
        prov.subscription_status = "ACTIVE"
        prov.save(update_fields=["subscription_next_due_date", "subscription_status"])
        logger.info(
            "[InterBilling] Cobrança RECEBIDA provedor=%s codigo=%s → ACTIVE",
            prov.id,
            charge.codigo_solicitacao,
        )
    elif charge.status == InterBillingCharge.STATUS_OVERDUE:
        prov.subscription_status = "OVERDUE"
        prov.save(update_fields=["subscription_status"])


def sync_open_inter_charges_from_api(provedor: Provedor) -> dict[str, Any]:
    """
    Busca no Inter o status atual das cobranças abertas do provedor.
    Necessário quando o webhook não chegou — evita suspender quem já pagou.
    """
    inter = InterService()
    if not inter.is_ready():
        return {"skipped": True, "reason": "inter_not_configured"}

    qs = list(
        InterBillingCharge.objects.filter(
            provedor=provedor,
            status__in=[InterBillingCharge.STATUS_PENDING, InterBillingCharge.STATUS_OVERDUE],
        )
        .select_related("provedor")
        .order_by("data_vencimento")[:20]
    )
    updated = 0
    received = 0
    for ch in qs:
        before = ch.status
        ch = refresh_charge_from_inter(ch, inter=inter)
        if ch.status != before:
            updated += 1
        if ch.status == InterBillingCharge.STATUS_RECEIVED:
            received += 1

    try:
        provedor.refresh_from_db(fields=["subscription_status", "subscription_next_due_date"])
    except Exception:
        pass

    return {"checked": len(qs), "updated": updated, "received": received}

def list_inter_payments_for_provedor(provedor: Provedor) -> list[dict]:
    items = []
    for ch in InterBillingCharge.objects.filter(provedor=provedor).order_by("-data_vencimento")[:50]:
        items.append(
            {
                "id": ch.codigo_solicitacao,
                "value": float(ch.valor),
                "dueDate": ch.data_vencimento.isoformat() if ch.data_vencimento else None,
                "status": ch.status,
                "billingType": "BOLETO",
                "provider": "inter",
                "linhaDigitavel": ch.linha_digitavel,
                "pixCopiaECola": ch.pix_copia_cola,
                "seuNumero": ch.seu_numero,
            }
        )
    return items


def clear_inter_subscription(provedor: Provedor, *, cancel_open_charges: bool = False) -> None:
    if cancel_open_charges:
        inter = InterService()
        if inter.is_ready():
            qs = InterBillingCharge.objects.filter(
                provedor=provedor,
                status__in=[InterBillingCharge.STATUS_PENDING, InterBillingCharge.STATUS_OVERDUE],
            )
            for ch in qs:
                inter.cancelar_cobranca(ch.codigo_solicitacao, motivo="Assinatura cancelada Superadmin")
                ch.status = InterBillingCharge.STATUS_CANCELLED
                ch.situacao = "CANCELADO"
                ch.save(update_fields=["status", "situacao", "updated_at"])

    provedor.billing_provider = Provedor.BILLING_PROVIDER_ASAAS
    if (provedor.asaas_subscription_id or "").startswith("INTER-SUB-"):
        provedor.asaas_subscription_id = None
    provedor.subscription_status = ""
    provedor.subscription_value = 0
    provedor.subscription_cycle = "MONTHLY"
    provedor.subscription_billing_type = "BOLETO"
    provedor.subscription_next_due_date = None
    provedor.save(
        update_fields=[
            "billing_provider",
            "asaas_subscription_id",
            "subscription_status",
            "subscription_value",
            "subscription_cycle",
            "subscription_billing_type",
            "subscription_next_due_date",
        ]
    )


def run_inter_charge_renewal_cycle(*, days_ahead: int = 5) -> dict[str, Any]:
    """
    Emite próxima cobrança para assinaturas Inter cujo próximo vencimento
    está dentro de `days_ahead` dias e ainda não tem cobrança daquele mês.
    """
    today = timezone.localdate()
    horizon = today + timedelta(days=max(0, int(days_ahead)))
    qs = Provedor.objects.filter(
        billing_provider=Provedor.BILLING_PROVIDER_INTER,
        asaas_subscription_id__startswith="INTER-SUB-",
    ).exclude(subscription_status__iexact="INACTIVE")

    created = 0
    skipped = 0
    errors = 0
    inter = InterService()
    if not inter.is_ready():
        return {"skipped": True, "reason": "inter_not_configured"}

    for prov in qs:
        due = prov.subscription_next_due_date
        if not due:
            skipped += 1
            continue
        # Se já passou ou está perto do vencimento, emitir a fatura do ciclo atual se faltar
        target_due = due
        if due < today:
            # Avança ciclos até o próximo vencimento futuro
            while target_due < today:
                target_due = _add_months(target_due, 1)
            prov.subscription_next_due_date = target_due
            prov.save(update_fields=["subscription_next_due_date"])

        if target_due > horizon:
            skipped += 1
            continue

        try:
            emitir_cobranca_para_provedor(
                prov,
                valor=float(prov.subscription_value or 0),
                data_vencimento=target_due,
                inter=inter,
            )
            # Agenda próximo ciclo após emitir
            next_due = _add_months(target_due, 1)
            if prov.subscription_next_due_date != next_due:
                # Mantém next_due como o da cobrança aberta até pagar;
                # só avança quando RECEBIDO (webhook). Aqui só garante emissão.
                pass
            created += 1
        except Exception:
            errors += 1
            logger.exception("[InterBilling] Falha ao renovar cobrança provedor=%s", prov.id)

    return {"created": created, "skipped": skipped, "errors": errors}


def sync_charge_from_webhook_payload(payload: dict) -> InterBillingCharge | None:
    """Atualiza InterBillingCharge a partir do callback do Inter."""
    codigo = (
        (payload.get("codigoSolicitacao") or "")
        or (payload.get("cobranca") or {}).get("codigoSolicitacao")
        or ""
    ).strip()
    if not codigo:
        return None

    charge = InterBillingCharge.objects.filter(codigo_solicitacao=codigo).select_related("provedor").first()
    if not charge:
        logger.warning("[InterWebhook] Cobrança desconhecida codigo=%s", codigo)
        return None

    normalized = InterService.normalize_cobranca_item(payload, codigo_solicitacao=codigo)
    new_status = normalized.get("status") or charge.status
    if new_status == "DELETED":
        new_status = InterBillingCharge.STATUS_CANCELLED
    charge.situacao = normalized.get("situacao") or charge.situacao
    charge.status = new_status
    if normalized.get("linhaDigitavel"):
        charge.linha_digitavel = normalized["linhaDigitavel"]
    if normalized.get("pixCopiaECola"):
        charge.pix_copia_cola = normalized["pixCopiaECola"]
    charge.payload = payload
    charge.save(
        update_fields=[
            "situacao",
            "status",
            "linha_digitavel",
            "pix_copia_cola",
            "payload",
            "updated_at",
        ]
    )

    _apply_charge_status_to_provedor(charge)

    return charge
