"""
Faturas Asaas para o agente de suporte da plataforma NioHub.

Busca cliente por CPF/CNPJ, lista cobranças e envia PIX/boleto na conversa
reutilizando fatura_service.enviar_fatura (mesmo canal da conversa).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from integrations.asaas_service import AsaasService

logger = logging.getLogger(__name__)

_STATUS_LABEL = {
    "PENDING": "Em aberto",
    "OVERDUE": "Vencida",
    "RECEIVED": "Paga",
    "CONFIRMED": "Confirmada",
    "RECEIVED_IN_CASH": "Paga",
    "REFUNDED": "Estornada",
    "REFUND_REQUESTED": "Estorno solicitado",
    "CHARGEBACK_REQUESTED": "Chargeback",
    "CHARGEBACK_DISPUTE": "Chargeback",
    "AWAITING_CHARGEBACK_REVERSAL": "Chargeback",
    "DUNNING_REQUESTED": "Em cobrança",
    "DUNNING_RECEIVED": "Recuperada",
    "AWAITING_RISK_ANALYSIS": "Em análise",
}

_OPEN_STATUSES = ("PENDING", "OVERDUE")


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _valid_cpf_cnpj(value: Any) -> bool:
    d = _digits(value)
    return len(d) in (11, 14) and d.isdigit()


def _format_due_br(due: str) -> str:
    raw = (due or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            y, m, d = raw[:10].split("-")
            return f"{d}/{m}/{y}"
        except ValueError:
            pass
    return raw


def _format_money_br(value: Any) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0
    return f"R$ {amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _summarize_payment(p: Dict[str, Any]) -> Dict[str, Any]:
    status = (p.get("status") or "").strip().upper()
    return {
        "id": p.get("id"),
        "descricao": (p.get("description") or "").strip() or None,
        "vencimento": p.get("dueDate"),
        "vencimento_br": _format_due_br(p.get("dueDate") or ""),
        "valor": p.get("value"),
        "valor_br": _format_money_br(p.get("value")),
        "status": status,
        "status_label": _STATUS_LABEL.get(status, status or "—"),
        "billing_type": p.get("billingType"),
        "invoice_url": p.get("invoiceUrl") or None,
        "bank_slip_url": p.get("bankSlipUrl") or None,
    }


def _pick_customer(
    customers: List[Dict[str, Any]],
    *,
    customer_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not customers:
        return None
    cid = (customer_id or "").strip()
    if cid:
        for c in customers:
            if str(c.get("id") or "").strip() == cid:
                return c
    return customers[0]


def _local_provedor_hint(cpf_cnpj: str) -> Optional[Dict[str, Any]]:
    """Opcional: enriquece com nome do provedor cadastrado no painel."""
    try:
        from django.db.models import Q

        from core.models import Provedor

        digits = _digits(cpf_cnpj)
        variants = {digits}
        if len(digits) == 11:
            variants.add(f"{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}")
        elif len(digits) == 14:
            variants.add(
                f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
            )
        q = Q()
        for v in variants:
            q |= Q(cpf_cnpj=v)
        p = Provedor.objects.filter(q).only("id", "nome", "asaas_customer_id", "cpf_cnpj").first()
        if not p:
            # Fallback: poucos provedores — match por dígitos se formato divergir
            for cand in Provedor.objects.exclude(cpf_cnpj__isnull=True).exclude(cpf_cnpj="").only(
                "id", "nome", "asaas_customer_id", "cpf_cnpj"
            )[:200]:
                if _digits(cand.cpf_cnpj) == digits:
                    p = cand
                    break
        if not p:
            return None
        return {
            "id": p.id,
            "nome": p.nome,
            "asaas_customer_id": (p.asaas_customer_id or "").strip() or None,
        }
    except Exception:
        logger.debug("[AsaasSupportFatura] Falha ao buscar provedor local", exc_info=True)
    return None


def buscar_faturas_por_cpf_cnpj(
    cpf_cnpj: str,
    *,
    customer_id: Optional[str] = None,
    incluir_pagas: bool = False,
    limit: int = 12,
) -> Dict[str, Any]:
    """
    Localiza o cliente no Asaas pelo CPF/CNPJ e lista cobranças.
    Prioriza OVERDUE e PENDING; opcionalmente inclui pagas recentes.
    """
    if not _valid_cpf_cnpj(cpf_cnpj):
        return {"success": False, "erro": "CPF/CNPJ inválido. Informe 11 ou 14 dígitos."}

    digits = _digits(cpf_cnpj)
    asaas = AsaasService()
    if not (asaas.access_token or "").strip():
        return {
            "success": False,
            "erro": "Asaas não configurado neste painel (token ausente).",
        }

    found = asaas.find_customers_by_cpf_cnpj(digits)
    if not found.get("success"):
        return {
            "success": False,
            "erro": found.get("error") or "Falha ao consultar clientes no Asaas.",
        }

    customers = list(found.get("data") or [])
    local = _local_provedor_hint(digits)

    # Preferir customer_id local se o Asaas não retornou e o provedor tem ID gravado
    if not customers and local and local.get("asaas_customer_id"):
        cres = asaas.get_customer(local["asaas_customer_id"])
        if cres.get("success") and cres.get("data"):
            customers = [cres["data"]]

    if not customers:
        return {
            "success": False,
            "erro": "Nenhum cliente encontrado no Asaas com este CPF/CNPJ.",
            "cpf_cnpj": digits,
        }

    if len(customers) > 1 and not (customer_id or "").strip():
        return {
            "success": True,
            "precisa_escolher_cliente": True,
            "cpf_cnpj": digits,
            "clientes": [
                {
                    "id": c.get("id"),
                    "nome": c.get("name"),
                    "email": c.get("email"),
                    "cpf_cnpj": c.get("cpfCnpj"),
                }
                for c in customers[:8]
            ],
            "nota": (
                "Há mais de um cadastro Asaas com este documento. "
                "Peça ao provedor para confirmar qual empresa e chame de novo "
                "com customer_id."
            ),
        }

    customer = _pick_customer(customers, customer_id=customer_id)
    if not customer:
        return {
            "success": False,
            "erro": "Cliente Asaas não encontrado com o customer_id informado.",
            "cpf_cnpj": digits,
        }

    cid = str(customer.get("id") or "").strip()
    open_payments: List[Dict[str, Any]] = []
    for st in _OPEN_STATUSES:
        res = asaas.list_payments(customer=cid, status=st)
        if res.get("success"):
            open_payments.extend(res.get("data") or [])

    # Ordenar: vencidas primeiro, depois por data
    def _sort_key(p: Dict[str, Any]) -> Tuple:
        st = (p.get("status") or "").upper()
        due = (p.get("dueDate") or "")[:10]
        return (0 if st == "OVERDUE" else 1, due)

    open_payments = sorted(open_payments, key=_sort_key)
    # Dedup por id
    seen = set()
    deduped = []
    for p in open_payments:
        pid = p.get("id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        deduped.append(p)
    open_payments = deduped[: max(1, min(int(limit or 12), 30))]

    paid: List[Dict[str, Any]] = []
    if incluir_pagas or not open_payments:
        for st in ("RECEIVED", "CONFIRMED", "RECEIVED_IN_CASH"):
            res = asaas.list_payments(customer=cid, status=st)
            if res.get("success"):
                paid.extend(res.get("data") or [])
        paid = sorted(paid, key=lambda p: (p.get("dueDate") or ""), reverse=True)[:5]

    faturas = [_summarize_payment(p) for p in open_payments]
    faturas_pagas = [_summarize_payment(p) for p in paid] if paid else []

    out: Dict[str, Any] = {
        "success": True,
        "cpf_cnpj": digits,
        "cliente": {
            "id": cid,
            "nome": customer.get("name"),
            "email": customer.get("email"),
            "cpf_cnpj": customer.get("cpfCnpj") or digits,
        },
        "faturas": faturas,
        "quantidade_em_aberto": len(faturas),
        "em_dia": len(faturas) == 0,
    }
    if local:
        out["provedor_painel"] = local
    if faturas_pagas:
        out["faturas_pagas_recentes"] = faturas_pagas
    if not faturas:
        out["nota"] = (
            "Não há cobranças em aberto ou vencidas no Asaas para este documento. "
            "Informe ao provedor. Se ele pedir uma fatura específica já paga, "
            "use as faturas_pagas_recentes (se houver) ou transfira ao financeiro."
        )
    else:
        out["nota"] = (
            "Liste as faturas em aberto de forma clara (valor, vencimento, status). "
            "Peça qual deseja receber e chame enviar_fatura_asaas com o payment_id. "
            "Se houver só uma, confirme brevemente e envie."
        )
    return out


def _enrich_payment_for_envio(asaas: AsaasService, payment: Dict[str, Any]) -> Dict[str, Any]:
    """Monta payload compatível com fatura_service.enviar_fatura."""
    pid = str(payment.get("id") or "").strip()
    due = payment.get("dueDate") or ""
    due_br = _format_due_br(due)
    value = payment.get("value")
    codigo_pix = ""
    linha = ""

    pix_res = asaas.get_payment_pix_qr_code(pid)
    if pix_res.get("success"):
        pdata = pix_res.get("data") or {}
        codigo_pix = str(pdata.get("payload") or "").strip()

    id_res = asaas.get_payment_identification_field(pid)
    if id_res.get("success"):
        idata = id_res.get("data") or {}
        linha = (
            idata.get("identificationField")
            or idata.get("barCode")
            or idata.get("nossoNumero")
            or ""
        )
        linha = str(linha).strip()

    link = (payment.get("bankSlipUrl") or payment.get("invoiceUrl") or "").strip() or None

    link_item = {
        "fatura": pid,
        "id": pid,
        "codigopix": codigo_pix or None,
        "pix_copia_cola": codigo_pix or None,
        "linhadigitavel": linha or None,
        "link": link,
        "valor": value,
        "vencimento": due_br,
        "vencimento_original": due[:10] if due else due_br,
        "descricao": (payment.get("description") or "").strip() or f"Fatura {pid}",
    }
    return {
        "status": 1,
        "links": [link_item],
        "fatura_id": pid,
        "valor": value,
        "vencimento": due_br,
        "pix_copia_cola": codigo_pix or None,
        "mensagem": (
            f"💳 *Sua fatura NioHub:*\n\n"
            f"ID: {pid}\n"
            f"Vencimento: {due_br}\n"
            f"Valor: {_format_money_br(value)}\n\n"
            f"Segue o pagamento."
        ),
    }


def enviar_fatura_asaas(
    provedor,
    *,
    payment_id: str,
    phone: str,
    conversation=None,
    tipo_pagamento: str = "ambos",
    cpf_cnpj: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Busca a cobrança no Asaas e envia na conversa (PIX + boleto por padrão).
    """
    pid = (payment_id or "").strip()
    if not pid:
        return {"success": False, "erro": "payment_id obrigatório."}
    if not phone or phone == "unknown":
        return {"success": False, "erro": "Telefone da conversa não identificado."}

    asaas = AsaasService()
    if not (asaas.access_token or "").strip():
        return {"success": False, "erro": "Asaas não configurado neste painel (token ausente)."}

    pay_res = asaas.get_payment(pid)
    if not pay_res.get("success"):
        return {
            "success": False,
            "erro": pay_res.get("error") or f"Cobrança {pid} não encontrada no Asaas.",
        }
    payment = pay_res.get("data") or {}
    if not payment:
        return {"success": False, "erro": f"Cobrança {pid} sem dados no Asaas."}

    # Segurança leve: se CPF foi informado, conferir se o customer bate
    if cpf_cnpj and _valid_cpf_cnpj(cpf_cnpj):
        cust_id = str(payment.get("customer") or "").strip()
        if cust_id:
            found = asaas.find_customers_by_cpf_cnpj(_digits(cpf_cnpj))
            ids = {str(c.get("id") or "") for c in (found.get("data") or [])}
            if ids and cust_id not in ids:
                return {
                    "success": False,
                    "erro": "A cobrança informada não pertence ao CPF/CNPJ consultado.",
                }

    dados = _enrich_payment_for_envio(asaas, payment)
    if not dados["links"][0].get("codigopix") and not dados["links"][0].get("linhadigitavel") and not dados["links"][0].get("link"):
        return {
            "success": False,
            "erro": (
                "Não foi possível obter PIX, boleto nem link desta cobrança no Asaas. "
                "Transfira ao financeiro."
            ),
            "payment_id": pid,
        }

    tp = (tipo_pagamento or "ambos").strip().lower()
    if tp not in ("pix", "boleto", "ambos"):
        tp = "ambos"

    from core.fatura_service import fatura_service as fs

    envio = fs.enviar_fatura(provedor, phone, dados, conversation, tp)
    ok = (isinstance(envio, bool) and envio) or (isinstance(envio, dict) and envio.get("success"))
    if not ok:
        err = envio.get("error") if isinstance(envio, dict) else "Falha ao enviar fatura."
        return {"success": False, "erro": err, "payment_id": pid}

    return {
        "success": True,
        "enviada": True,
        "payment_id": pid,
        "valor": payment.get("value"),
        "vencimento_br": _format_due_br(payment.get("dueDate") or ""),
        "tipo_pagamento": tp,
        "nota": (
            "Fatura Asaas já enviada NESTA conversa (PIX/boleto conforme disponível). "
            "Confirme de forma natural e pergunte se precisa de mais alguma coisa. "
            "NÃO diga 'pelo canal informado' nem 'receberá em breve'."
        ),
    }
