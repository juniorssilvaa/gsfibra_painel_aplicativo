import json
import logging
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from core.models import Provedor, SystemConfig
from integrations.asaas_service import AsaasService
from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION
from integrations.whatsapp_cloud_send import (
    _extract_pix_info_from_code,
    send_interactive_order_details_raw,
    send_template_message,
)

logger = logging.getLogger(__name__)

def _parse_billing_run_hm(run_time: str) -> tuple[int, int]:
    raw = (run_time or "09:00").strip()
    parts = raw.split(":")
    try:
        h = int(parts[0]) % 24
    except (ValueError, IndexError):
        h = 9
    try:
        m = int(parts[1]) % 60 if len(parts) > 1 else 0
    except (ValueError, IndexError):
        m = 0
    return h, m


def _billing_run_time_label(run_time: str) -> str:
    h, m = _parse_billing_run_hm(run_time)
    return f"{h:02d}:{m:02d}"


def _local_now_in_billing_run_window(now, run_time: str, window_minutes: int) -> bool:
    """
    window_minutes <= 0: só no minuto do relógio igual ao configurado (ex.: 08:30).
    window_minutes > 0: do horário configurado até esse número de minutos depois
    (útil se o servidor demorar alguns segundos para acordar a tarefa).
    """
    h, m = _parse_billing_run_hm(run_time)
    slot_start = now.replace(hour=h, minute=m, second=0, microsecond=0)
    w = int(window_minutes or 0)
    if w <= 0:
        return now.hour == h and now.minute == m
    w = max(1, min(w, 45))
    slot_end = slot_start + timedelta(minutes=w)
    return slot_start <= now < slot_end


def _system_display_name(config: SystemConfig) -> str:
    """Nome do sistema (ex.: NIO HUB) vindo do JSON em SystemConfig.value.site_name."""
    try:
        raw = json.loads(config.value or "{}")
        if isinstance(raw, dict):
            name = (raw.get("site_name") or "").strip()
            if name:
                return name[:120]
    except Exception:
        pass
    return "Nio Chat"


def _parse_due_offsets_str(raw: str) -> List[int]:
    out: List[int] = []
    for part in (raw or "").split(","):
        part = part.strip()
        if part == "":
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def _effective_due_offsets(config: SystemConfig) -> List[int]:
    s = (getattr(config, "billing_reminder_due_offsets", None) or "").strip()
    if s:
        return _parse_due_offsets_str(s)
    legacy = max(1, int(getattr(config, "billing_days_before_due", None) or 3))
    return [-legacy]


def _parse_payment_due_date(due: str) -> Optional[date]:
    raw = (due or "").strip()[:10]
    if len(raw) != 10 or raw[4] != "-" or raw[7] != "-":
        return None
    try:
        y, m, d = raw.split("-")
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def _pending_payments_for_offsets(
    asaas: AsaasService, today: date, offsets: List[int]
) -> List[Dict[str, Any]]:
    """
    Pendentes cuja data de vencimento coincide com (hoje - offset) para algum offset <= 0.
    Ex.: -1 => vence amanhã; 0 => vence hoje. Offsets > 0 são só para filtro de vencidos.
    """
    non_positive = sorted({u for u in offsets if u <= 0})
    if not non_positive:
        return []
    targets = {today - timedelta(days=u) for u in non_positive}
    if not targets:
        return []
    d_min = min(targets)
    d_max = max(targets)
    res = asaas.list_payments(
        status="PENDING",
        due_date_ge=d_min.isoformat(),
        due_date_le=d_max.isoformat(),
    )
    if not res.get("success"):
        return []
    out: List[Dict[str, Any]] = []
    for p in res.get("data", []) or []:
        dd = _parse_payment_due_date(p.get("dueDate") or "")
        if dd and dd in targets:
            out.append(p)
    return out


def _filter_overdue_by_offsets(
    overdue_items: List[Dict[str, Any]], today: date, offsets: List[int]
) -> List[Dict[str, Any]]:
    non_negative = sorted({u for u in offsets if u >= 0})
    if not non_negative:
        return list(overdue_items)
    out: List[Dict[str, Any]] = []
    for p in overdue_items:
        dd = _parse_payment_due_date(p.get("dueDate") or "")
        if not dd:
            continue
        delta = (today - dd).days
        # Permite 0 como "vencida hoje" quando o Asaas já marca status OVERDUE.
        if delta >= 0 and delta in non_negative:
            out.append(p)
    return out


def _normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if not digits:
        return ""
    if not digits.startswith("55") and len(digits) <= 11:
        digits = f"55{digits}"
    return f"+{digits}"


def _format_currency(value: Any) -> str:
    try:
        amount = Decimal(str(value or "0"))
    except Exception:
        amount = Decimal("0")
    return f"R$ {amount:.2f}"


def _render_message(template: str, payload: dict) -> str:
    msg = template or ""
    for key, value in payload.items():
        msg = msg.replace(f"{{{{{key}}}}}", str(value))
    return msg


def _format_due_br(due: str) -> str:
    raw = (due or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            y, m, d = raw[:10].split("-")
            return f"{d}/{m}/{y}"
        except ValueError:
            pass
    return raw


def _amount_body_br(value: Any) -> str:
    try:
        amount = Decimal(str(value or "0"))
    except Exception:
        amount = Decimal("0")
    return f"{amount:.2f}".replace(".", ",")


def _url_looks_like_public_pdf(url: str) -> bool:
    if not url or not url.lower().startswith("https://"):
        return False
    path = url.split("?", 1)[0].lower()
    if path.endswith(".pdf"):
        return True
    try:
        r = requests.head(url, allow_redirects=True, timeout=15)
        ct = (r.headers.get("Content-Type") or "").lower()
        return "application/pdf" in ct
    except Exception:
        return False


def _pick_pdf_from_asaas_documents(asaas: AsaasService, payment_id: str) -> str:
    res = asaas.list_payment_documents(payment_id)
    if not res.get("success"):
        return ""
    for doc in res.get("data") or []:
        ext = (doc.get("extension") or "").lower()
        if ext and ext != "pdf":
            continue
        for key in ("downloadUrl", "previewUrl"):
            cand = (doc.get(key) or "").strip()
            if cand.lower().startswith("https://"):
                return cand
    return ""


def _resolve_pdf_document_url(asaas: AsaasService, payment: Dict[str, Any]) -> str:
    """
    URL HTTPS de PDF aceita pela Meta no cabeçalho (não usar invoiceUrl /i/... que é HTML).
    """
    pid = payment.get("id") or ""
    if pid:
        u = _pick_pdf_from_asaas_documents(asaas, str(pid))
        if u:
            return u
    for key in ("bankSlipUrl", "invoiceUrl"):
        cand = (payment.get(key) or "").strip()
        if cand.lower().startswith("https://") and _url_looks_like_public_pdf(cand):
            return cand
    return ""


def _billing_order_details_parameters(
    payment: Dict[str, Any],
    provedor: Optional[Provedor],
    pix_code: str,
    display_merchant: Optional[str] = None,
) -> Dict[str, Any]:
    valor_centavos = int(Decimal(str(payment.get("value") or 0)) * 100)
    base = (display_merchant or "").strip() or ((provedor.nome if provedor else "") or "")
    merchant = (base or "Nio Chat")[:60]
    pix_key, pix_key_type = _extract_pix_info_from_code(pix_code)
    if not pix_key:
        pix_key = merchant[:77] if merchant else "00000000000"
        pix_key_type = pix_key_type or "EVP"
    pid = str(payment.get("id") or "")[:80]
    return {
        "reference_id": pid,
        "type": "digital-goods",
        "payment_type": "br",
        "payment_settings": [
            {
                "type": "pix_dynamic_code",
                "pix_dynamic_code": {
                    "code": pix_code,
                    "merchant_name": merchant,
                    "key": pix_key,
                    "key_type": pix_key_type,
                },
            }
        ],
        "currency": "BRL",
        "total_amount": {"value": valor_centavos, "offset": 100},
        "order": {
            "status": "pending",
            "tax": {"value": 0, "offset": 100, "description": "Impostos"},
            "items": [
                {
                    "retailer_id": pid,
                    "name": f"Fatura {pid}"[:120],
                    "amount": {"value": valor_centavos, "offset": 100},
                    "quantity": 1,
                }
            ],
            "subtotal": {"value": valor_centavos, "offset": 100},
        },
    }


_INTERACTIVE_BODY_MAX = 1024


def _billing_interactive_body_from_template(
    mode: str,
    template: str,
    payload: dict,
) -> str:
    body = _render_message(template or "", payload).strip()
    if body:
        return body[:_INTERACTIVE_BODY_MAX]
    nome = payload.get("nome") or "Cliente"
    valor = payload.get("valor") or ""
    venc = payload.get("vencimento_br") or payload.get("vencimento") or ""
    if mode == "overdue":
        fb = (
            f"Olá, *{nome}*!\n\n"
            f"Cobrança em atraso no valor de *{valor}* (vencimento *{venc}*).\n\n"
            "Toque em *Revisar e pagar* para copiar o *código PIX*."
        )
    else:
        fb = (
            f"Olá, *{nome}*!\n\n"
            f"Lembrete de cobrança no valor de *{valor}* (vencimento *{venc}*).\n\n"
            "Toque em *Revisar e pagar* para copiar o *código PIX*."
        )
    return fb[:_INTERACTIVE_BODY_MAX]


def _build_cobranca_order_template_components(
    payment: Dict[str, Any],
    provedor: Optional[Provedor],
    pix_code: str,
    doc_url: str,
    display_merchant: Optional[str] = None,
) -> List[dict]:
    """
    Template Utility ORDER_DETAILS (ex.: cobranca_order): cabeçalho PDF (URL pública HTTPS),
    corpo {{1}} valor (ex.: 80,00), {{2}} vencimento (DD/MM/AAAA), botão order_details com PIX dinâmico.
    """
    order_details = _billing_order_details_parameters(
        payment, provedor, pix_code, display_merchant=display_merchant
    )

    return [
        {
            "type": "header",
            "parameters": [
                {
                    "type": "document",
                    "document": {
                        "link": doc_url,
                        "filename": "fatura.pdf",
                    },
                }
            ],
        },
        {
            "type": "body",
            "parameters": [
                {"type": "text", "text": _amount_body_br(payment.get("value"))},
                {"type": "text", "text": _format_due_br(payment.get("dueDate") or "")},
            ],
        },
        {
            "type": "button",
            "sub_type": "order_details",
            "index": 0,
            "parameters": [
                {"type": "action", "action": {"order_details": order_details}}
            ],
        },
    ]


def _send_whatsapp_text(phone_number_id: str, token: str, to_number: str, body: str) -> bool:
    url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "text",
        "text": {"preview_url": False, "body": body[:4096]},
    }
    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code == 200:
        return True
    logger.warning(
        "[BillingReminder] Falha ao enviar WhatsApp | to=%s status=%s body=%s",
        to_number,
        response.status_code,
        response.text[:500],
    )
    return False


def run_billing_reminder_cycle() -> dict:
    """
    Executa um ciclo de envio de cobrança do canal exclusivo do superadmin.
    """
    config = SystemConfig.objects.filter(key="system_config").first() or SystemConfig.objects.first()
    if not config:
        return {"success": False, "reason": "system_config_not_found"}

    if not config.billing_channel_enabled:
        return {"success": True, "reason": "billing_channel_disabled"}

    if not config.billing_whatsapp_token or not config.billing_whatsapp_phone_number_id:
        return {"success": False, "reason": "billing_whatsapp_not_configured"}

    now = timezone.localtime()
    run_time = (config.billing_run_time or "09:00").strip()
    run_time_key = _billing_run_time_label(run_time)
    run_days_raw = (config.billing_run_days or "0,1,2,3,4,5,6").strip()
    allowed_days = {d.strip() for d in run_days_raw.split(",") if d.strip() != ""}
    weekday = str(now.weekday())

    if weekday not in allowed_days:
        return {"success": True, "reason": "not_scheduled_day"}
    window_m = int(getattr(config, "billing_run_window_minutes", 0) or 0)
    if not _local_now_in_billing_run_window(now, run_time, window_m):
        if window_m <= 0:
            detail = (
                f"fora do minuto exato {run_time_key} "
                f"(TIME_ZONE={getattr(settings, 'TIME_ZONE', '')})"
            )
        else:
            detail = (
                f"fora do horario {run_time_key} com margem de {window_m} min apos "
                f"(TIME_ZONE={getattr(settings, 'TIME_ZONE', '')})"
            )
        return {"success": True, "reason": "not_scheduled_time", "detail": detail}

    dedupe_key = f"billing_reminder_cycle:{now.strftime('%Y%m%d')}:{run_time_key}"
    if not cache.add(dedupe_key, "1", timeout=26 * 3600):
        return {"success": True, "reason": "already_executed_today"}

    asaas = AsaasService()
    if not asaas.access_token:
        return {"success": False, "reason": "asaas_access_token_missing"}

    offsets = _effective_due_offsets(config)
    today_d = now.date()
    sent_total = 0
    sent_template = 0
    sent_interactive = 0
    sent_text_fallback = 0

    use_tpl = getattr(config, "billing_whatsapp_use_template", True)
    tpl_name = (getattr(config, "billing_whatsapp_template_name", None) or "cobranca_order").strip()
    tpl_lang = (getattr(config, "billing_whatsapp_template_language", None) or "pt_BR").strip()

    billing_canal = SimpleNamespace(
        token=config.billing_whatsapp_token,
        phone_number_id=config.billing_whatsapp_phone_number_id,
        waba_id=config.billing_whatsapp_waba_id or "",
    )

    overdue_res = asaas.list_payments(status="OVERDUE")
    overdue_items = overdue_res.get("data", []) if overdue_res.get("success") else []
    overdue_items = _filter_overdue_by_offsets(overdue_items, today_d, offsets)

    due_soon_items = _pending_payments_for_offsets(asaas, today_d, offsets)

    all_items = [("overdue", p) for p in overdue_items] + [("due_soon", p) for p in due_soon_items]

    system_name = _system_display_name(config)

    for mode, payment in all_items:
        customer_id = payment.get("customer")
        if not customer_id:
            continue

        customer_res = asaas.get_customer(customer_id)
        if not customer_res.get("success"):
            continue
        customer = customer_res.get("data", {}) or {}

        customer_name = customer.get("name") or "Cliente"
        customer_phone = _normalize_phone(customer.get("mobilePhone") or customer.get("phone"))
        if not customer_phone:
            continue

        provedor = Provedor.objects.filter(asaas_customer_id=customer_id).first()
        provedor_name = provedor.nome if provedor else customer_name

        due_raw = payment.get("dueDate") or ""
        payload = {
            "nome": customer_name,
            "provedor": provedor_name,
            "valor": _format_currency(payment.get("value")),
            "vencimento": due_raw,
            "vencimento_br": _format_due_br(due_raw),
            "fatura_id": payment.get("id") or "",
            "sistema": system_name,
            "marca": provedor_name,
        }

        template = config.billing_template_overdue if mode == "overdue" else config.billing_template_due_soon
        body = _render_message(template, payload).strip()

        pdf_url = _resolve_pdf_document_url(asaas, payment)
        pix_code = ""
        pix_res = asaas.get_payment_pix_qr_code(payment.get("id") or "")
        if pix_res.get("success"):
            pdata = pix_res.get("data") or {}
            pix_code = (pdata.get("payload") or pdata.get("brCode") or "").strip()

        want_template = bool(use_tpl and tpl_name and pix_code and pdf_url)

        ok = False
        if want_template:
            components = _build_cobranca_order_template_components(
                payment, provedor, pix_code, pdf_url, display_merchant=system_name
            )
            success, err, _resp = send_template_message(
                billing_canal,
                recipient_number=customer_phone,
                template_name=tpl_name,
                template_language=tpl_lang,
                template_components=components,
            )
            if success:
                ok = True
                sent_template += 1
            else:
                logger.warning(
                    "[BillingReminder] Falha no template %s | payment=%s err=%s; tentando mensagem rica (order_details)",
                    tpl_name,
                    payment.get("id"),
                    err,
                )

        if not ok and use_tpl and pix_code:
            body_ix = _billing_interactive_body_from_template(mode, template, payload)
            od_params = _billing_order_details_parameters(
                payment, provedor, pix_code, display_merchant=system_name
            )
            doc_ix = pdf_url if pdf_url and _url_looks_like_public_pdf(pdf_url) else None
            ok_ix, err_ix, _r = send_interactive_order_details_raw(
                config.billing_whatsapp_phone_number_id,
                config.billing_whatsapp_token,
                customer_phone,
                body_ix,
                od_params,
                document_link=doc_ix,
                document_filename="fatura.pdf",
                footer_text=(system_name[:58] if system_name else None),
            )
            if ok_ix:
                ok = True
                sent_interactive += 1
            else:
                logger.warning(
                    "[BillingReminder] Falha na mensagem interativa order_details | payment=%s err=%s",
                    payment.get("id"),
                    err_ix,
                )

        if not ok and body:
            ok = _send_whatsapp_text(
                phone_number_id=config.billing_whatsapp_phone_number_id,
                token=config.billing_whatsapp_token,
                to_number=customer_phone,
                body=body,
            )
            if ok:
                sent_text_fallback += 1

        if ok:
            sent_total += 1

    return {
        "success": True,
        "sent_total": sent_total,
        "sent_template": sent_template,
        "sent_interactive": sent_interactive,
        "sent_text_fallback": sent_text_fallback,
        "overdue_count": len(overdue_items),
        "due_soon_count": len(due_soon_items),
        "due_offsets": offsets,
        "billing_run_window_minutes": window_m,
        "run_at": now.isoformat(),
    }
