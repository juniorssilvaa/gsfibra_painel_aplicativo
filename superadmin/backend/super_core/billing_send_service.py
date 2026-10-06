"""
billing_send_service.py — Superadmin

Envia lembretes de cobrança via WhatsApp Oficial usando o canal do Superadmin.

Lógica idêntica ao script enviar_cobranca_whatsapp.ps1:
  Passo 1: Baixar o PDF da fatura (Asaas bankSlipUrl / invoiceUrl)
  Passo 2: Upload do PDF para a Meta API (POST /{phone_number_id}/media)
  Passo 3: Buscar estrutura do template na Meta e montar components dinamicamente
             (header/body/botão conforme aprovado; nome sempre do cliente Asaas)
  Passo 4: Enviar via POST /{phone_number_id}/messages
"""
import io
import json
import logging
import re
import time
import unicodedata
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from .models import BillingSendLog, Provedor

logger = logging.getLogger(__name__)


def _resolve_provedor_for_payment(payment: Dict[str, Any], customer_id: str) -> Optional[Provedor]:
    sub = payment.get("subscription")
    if isinstance(sub, dict):
        sub_id = str(sub.get("id") or "").strip()
    else:
        sub_id = str(sub or "").strip()
    if sub_id:
        found = Provedor.objects.filter(asaas_subscription_id=sub_id).first()
        if found:
            return found
    cid = str(customer_id or "").strip()
    if cid:
        return Provedor.objects.filter(asaas_customer_id=cid).first()
    return None


def _log_billing_send(
    *,
    payment: Dict[str, Any],
    customer_id: str,
    phone: str,
    template_name: str,
    offset: int,
    success: bool,
    error_message: str = "",
) -> None:
    try:
        due_raw = payment.get("dueDate") or ""
        due_d = None
        if due_raw:
            try:
                y, m, d = [int(x) for x in str(due_raw).split("-")[:3]]
                due_d = date(y, m, d)
            except Exception:
                due_d = None
        val = None
        try:
            if payment.get("value") is not None:
                val = Decimal(str(payment.get("value")))
        except Exception:
            val = None
        BillingSendLog.objects.create(
            provedor=_resolve_provedor_for_payment(payment, customer_id),
            asaas_payment_id=str(payment.get("id") or ""),
            asaas_customer_id=str(customer_id or ""),
            phone=phone or "",
            template_name=template_name or "",
            due_offset=int(offset or 0),
            due_date=due_d,
            value=val,
            success=bool(success),
            error_message=(error_message or "")[:2000],
        )
    except Exception:
        logger.exception("[BillingSend] Falha ao gravar BillingSendLog")


# ──────────────────────────────────────────────────────────────────────────────
# Constantes da API Meta
# ──────────────────────────────────────────────────────────────────────────────
GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

_META_VAR_RE = re.compile(r"\{\{(\d+)\}\}")
_SLOT_BY_POSITION = ("name", "money", "date", "title", "provider")


# ──────────────────────────────────────────────────────────────────────────────
# Template Meta — introspectão dinâmica
# ──────────────────────────────────────────────────────────────────────────────
def _strip_accents(text: str) -> str:
    nfd = unicodedata.normalize("NFD", text or "")
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _extract_meta_var_indices(text: str) -> List[int]:
    ordered: List[int] = []
    seen = set()
    for m in _META_VAR_RE.finditer(text or ""):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return ordered


def _body_text_from_template(template: Dict[str, Any]) -> str:
    for comp in template.get("components") or []:
        if str(comp.get("type", "")).upper() == "BODY":
            return (comp.get("text") or "").strip()
    return ""


def _template_header_format(template: Dict[str, Any]) -> str:
    for comp in template.get("components") or []:
        if str(comp.get("type", "")).upper() == "HEADER":
            return str(comp.get("format") or "").upper()
    return ""


def _order_details_button_index(template: Dict[str, Any]) -> Optional[int]:
    for comp in template.get("components") or []:
        if str(comp.get("type", "")).upper() != "BUTTONS":
            continue
        for idx, btn in enumerate(comp.get("buttons") or []):
            if str(btn.get("type", "")).upper() in ("ORDER_DETAILS", "PAYMENT_REQUEST"):
                return idx
    return None


def _line_context_before_var(template_body: str, var_index: int) -> str:
    marker = f"{{{{{var_index}}}}}"
    pos = (template_body or "").find(marker)
    if pos < 0:
        return ""
    line_start = (template_body or "").rfind("\n", 0, pos)
    line_start = 0 if line_start < 0 else line_start + 1
    return _strip_accents(template_body[line_start:pos]).lower()


def _classify_template_var_slot(template_body: str, var_index: int) -> str:
    marker = f"{{{{{var_index}}}}}"
    pos = (template_body or "").find(marker)
    if pos < 0:
        return "generic"

    line_before = _line_context_before_var(template_body, var_index)
    close_before = _strip_accents(template_body[max(0, pos - 32) : pos]).lower()
    after = _strip_accents(template_body[pos + len(marker) : pos + len(marker) + 40]).lower()

    _DATE_BEFORE = (
        r"vence\s+hoje|vence\s+em|pagamento\s+ate|valido\s+para\s+pagamento\s+ate|"
        r"vencimento|venceu|venc\.|data\s+de\s+vencimento"
    )

    if line_before:
        if re.search(_DATE_BEFORE, line_before):
            return "date"
        if re.search(r"valor\s+original", line_before):
            return "money"
        if re.search(r"valor|r\$", line_before) and not re.search(
            r"vencimento\s+original", line_before
        ):
            return "money"
        if re.search(r"ol[aá]|sr\(|sra|nome|cliente|prezado", line_before):
            return "name"
        if re.search(r"titulo|fatura\s*#|contrato|referencia|charge", line_before):
            return "title"
        if re.search(r"provedor|equipe\s+d[ao]", line_before):
            return "provider"

    if re.search(_DATE_BEFORE, close_before):
        return "date"
    if re.search(r"valor|r\$", close_before):
        return "money"

    ctx = f"{_strip_accents(template_body[max(0, pos - 55) : pos]).lower()} {after}"
    if re.search(_DATE_BEFORE, ctx):
        return "date"
    if re.search(r"ol[aá]|sr\(|sra|nome|cliente|prezado", ctx):
        return "name"
    if re.search(r"valor|r\$|amount|total|no\s+valor\s+de", ctx):
        return "money"
    if re.search(r"titulo|fatura\s*#|contrato|referencia|charge", ctx):
        return "title"
    if re.search(r"provedor|equipe\s+d[ao]", ctx):
        return "provider"
    return "generic"


def _resolve_body_param_value(
    slot: str,
    *,
    var_index: int,
    indices: List[int],
    customer_name: str,
    valor_br: str,
    vencimento_br: str,
    merchant_name: str,
    fatura_desc: str,
) -> str:
    """Nome do cliente sempre vem do Asaas (customer_name)."""
    if slot == "generic":
        pos = indices.index(var_index) if var_index in indices else 0
        slot = _SLOT_BY_POSITION[min(pos, len(_SLOT_BY_POSITION) - 1)]

    if slot == "name":
        return (customer_name or "Cliente").strip()[:256]
    if slot == "money":
        return valor_br
    if slot == "date":
        return vencimento_br
    if slot == "provider":
        return (merchant_name or "Nio Hub").strip()[:256]
    if slot == "title":
        return ((fatura_desc or "").strip() or "-")[:256]
    return "-"


def _build_body_parameters(
    template_def: Dict[str, Any],
    *,
    customer_name: str,
    valor_br: str,
    vencimento_br: str,
    merchant_name: str,
    fatura_desc: str,
) -> List[Dict[str, str]]:
    body_text = _body_text_from_template(template_def)
    indices = _extract_meta_var_indices(body_text)
    params: List[Dict[str, str]] = []
    for n in indices:
        slot = _classify_template_var_slot(body_text, n)
        text = _resolve_body_param_value(
            slot,
            var_index=n,
            indices=indices,
            customer_name=customer_name,
            valor_br=valor_br,
            vencimento_br=vencimento_br,
            merchant_name=merchant_name,
            fatura_desc=fatura_desc,
        )
        params.append({"type": "text", "text": text or "-"})
    return params


def _fetch_whatsapp_template(
    waba_id: str,
    token: str,
    template_name: str,
    template_language: str,
) -> Optional[Dict[str, Any]]:
    if not waba_id or not template_name:
        return None
    url = f"{GRAPH_BASE}/{waba_id}/message_templates"
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"name": template_name, "limit": 20},
            timeout=20,
        )
        if resp.status_code != 200:
            logger.warning(
                "[BillingSend] Meta templates API %s: %s",
                resp.status_code,
                (resp.text or "")[:300],
            )
            return None
        items = (resp.json() or {}).get("data") or []
        lang = (template_language or "pt_BR").strip()
        for tpl in items:
            if (tpl.get("name") or "") == template_name and (tpl.get("language") or "") == lang:
                return tpl
        for tpl in items:
            if (tpl.get("name") or "") == template_name:
                return tpl
    except Exception as exc:
        logger.warning("[BillingSend] Falha ao buscar template %s: %s", template_name, exc)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Helpers de formatação
# ──────────────────────────────────────────────────────────────────────────────
def _fmt_valor_br(value: Any) -> str:
    """'420.00' → '420,00'"""
    try:
        return f"{Decimal(str(value or '0')):.2f}".replace(".", ",")
    except Exception:
        return "0,00"


def _valor_centavos(value: Any) -> int:
    try:
        return int(Decimal(str(value or "0")) * 100)
    except Exception:
        return 0


def _fmt_due_br(due: str) -> str:
    """'2026-05-12' → '12/05/2026'"""
    raw = (due or "").strip()
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            y, m, d = raw[:10].split("-")
            return f"{d}/{m}/{y}"
        except ValueError:
            pass
    return raw


def _normalize_phone(phone: str) -> str:
    """
    Mantém DDI internacional (+1, +351, etc.).
    Só prefixa 55 quando parece telefone BR local (10/11 dígitos).
    """
    import re

    raw = str(phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""
    if raw.startswith("+"):
        return digits
    # BR local: DDD+fixo (10) ou DDD+9+móvel (11)
    is_br_local = bool(
        (len(digits) == 10 and re.fullmatch(r"[1-9][1-9]\d{8}", digits))
        or (len(digits) == 11 and re.fullmatch(r"[1-9][1-9]9\d{8}", digits))
    )
    if not digits.startswith("55") and is_br_local:
        digits = f"55{digits}"
    return digits  # sem '+' — API da Meta aceita só dígitos


def _invoice_number_from_payment(payment: Dict[str, Any]) -> str:
    """
    Número da fatura exibido no Asaas (ex.: 15426686).
    Fallback: externalReference → id pay_xxx.
    """
    for key in ("invoiceNumber", "invoice_number", "nossoNumero", "externalReference"):
        val = str((payment or {}).get(key) or "").strip()
        if val:
            return val
    return str((payment or {}).get("id") or "fatura").strip()


# ──────────────────────────────────────────────────────────────────────────────
# Extração de chave PIX do código EMV
# ──────────────────────────────────────────────────────────────────────────────
_PIX_CNPJ_RE = re.compile(r"\d{14}")
_PIX_CPF_RE  = re.compile(r"\d{11}")
_PIX_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PIX_PHONE_RE = re.compile(r"\+\d{10,15}")
_PIX_EVP_RE   = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


def _extract_pix_info(pix_code: str) -> Tuple[str, str]:
    """Retorna (pix_key, key_type) a partir do código PIX EMV."""
    if not pix_code:
        return "", "EVP"
    m = _PIX_EVP_RE.search(pix_code)
    if m:
        return m.group(), "EVP"
    m = _PIX_EMAIL_RE.search(pix_code)
    if m:
        return m.group(), "EMAIL"
    m = _PIX_PHONE_RE.search(pix_code)
    if m:
        return m.group(), "PHONE"
    # CNPJ antes de CPF (14 dígitos vs 11)
    m = _PIX_CNPJ_RE.search(pix_code)
    if m:
        return m.group(), "CNPJ"
    m = _PIX_CPF_RE.search(pix_code)
    if m:
        return m.group(), "CPF"
    return "", "EVP"


# ──────────────────────────────────────────────────────────────────────────────
# Passo 1+2: Baixar PDF e fazer upload para a Meta
# ──────────────────────────────────────────────────────────────────────────────
def _upload_pdf_bytes_to_meta(phone_number_id: str, token: str, pdf_bytes: bytes) -> Optional[str]:
    if not pdf_bytes:
        return None
    upload_url = f"{GRAPH_BASE}/{phone_number_id}/media"
    try:
        upload_resp = requests.post(
            upload_url,
            headers={"Authorization": f"Bearer {token}"},
            files={
                "file": ("fatura.pdf", io.BytesIO(pdf_bytes), "application/pdf"),
            },
            data={"messaging_product": "whatsapp"},
            timeout=60,
        )
        data = upload_resp.json() if upload_resp.content else {}
        if upload_resp.status_code == 200 and data.get("id"):
            media_id = str(data["id"])
            logger.info("[BillingSend] PDF enviado para Meta. media_id=%s", media_id)
            return media_id
        logger.warning("[BillingSend] Falha no upload do PDF: %s %s", upload_resp.status_code, data)
    except Exception as exc:
        logger.warning("[BillingSend] Exceção no upload do PDF: %s", exc)
    return None


def _upload_pdf_to_meta(phone_number_id: str, token: str, pdf_url: str) -> Optional[str]:
    """
    Baixa o PDF da URL informada e faz upload para a Meta API.
    Retorna o media_id ou None em caso de erro.
    """
    try:
        resp = requests.get(pdf_url, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        pdf_bytes = resp.content
    except Exception as exc:
        logger.warning("[BillingSend] Falha ao baixar PDF %s: %s", pdf_url, exc)
        return None
    return _upload_pdf_bytes_to_meta(phone_number_id, token, pdf_bytes)


def _inter_payments_for_offsets(today_d: date, offsets: List[int]) -> List[Dict[str, Any]]:
    """Monta lista de cobranças Inter no formato compatível com o ciclo WhatsApp."""
    from .models import InterBillingCharge, Provedor

    targets_pending = {today_d - timedelta(days=u) for u in offsets if u <= 0}
    positive = sorted({u for u in offsets if u > 0})
    qs = InterBillingCharge.objects.filter(
        status__in=[InterBillingCharge.STATUS_PENDING, InterBillingCharge.STATUS_OVERDUE],
        provedor__billing_provider=Provedor.BILLING_PROVIDER_INTER,
    ).select_related("provedor")

    out: List[Dict[str, Any]] = []
    for ch in qs:
        if not ch.data_vencimento:
            continue
        dd = ch.data_vencimento
        include = False
        if dd in targets_pending:
            include = True
        elif positive:
            delta = (today_d - dd).days
            if delta >= 0 and delta in positive:
                include = True
        if not include:
            continue
        # Atualiza linha/pix se vazios
        if not (ch.linha_digitavel or ch.pix_copia_cola):
            try:
                from .inter_billing_service import refresh_charge_from_inter
                ch = refresh_charge_from_inter(ch)
            except Exception:
                pass
        out.append({
            "id": ch.codigo_solicitacao,
            "provider": "inter",
            "provedor_id": ch.provedor_id,
            "customer": f"inter-prov-{ch.provedor_id}",
            "value": float(ch.valor),
            "dueDate": dd.isoformat(),
            "status": ch.status,
            "description": f"Cobrança Inter {ch.seu_numero}",
            "pixCopiaECola": ch.pix_copia_cola or "",
            "linhaDigitavel": ch.linha_digitavel or "",
            "subscription": ch.provedor.asaas_subscription_id or "",
        })
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Passo 3: Montar payload do template (idêntico ao script PS1)
# ──────────────────────────────────────────────────────────────────────────────
def _build_order_details(
    *,
    pix_code: str,
    linha_digitavel: str,
    fatura_desc: str,
    valor_centavos: int,
    merchant_name: str,
    payment_id: str,
    invoice_number: str,
) -> Dict[str, Any]:
    pix_key, pix_key_type = _extract_pix_info(pix_code)
    if not pix_key:
        pix_key = merchant_name[:77] or "00000000000000"
        pix_key_type = "EVP"

    digitable_line = "".join(ch for ch in str(linha_digitavel or "") if ch.isdigit())
    payment_settings: List[Dict] = [
        {
            "type": "pix_dynamic_code",
            "pix_dynamic_code": {
                "merchant_name": merchant_name[:60],
                "key": pix_key,
                "key_type": pix_key_type,
                "code": pix_code,
            },
        }
    ]
    if digitable_line:
        payment_settings.append({
            "type": "boleto",
            "boleto": {"digitable_line": digitable_line},
        })

    ref = (invoice_number or payment_id or "fatura").strip()[:80]
    item_name = (fatura_desc or f"Fatura {ref}")[:120]
    return {
        "reference_id": ref,
        "type": "digital-goods",
        "payment_type": "br",
        "currency": "BRL",
        "total_amount": {"value": valor_centavos, "offset": 100},
        "payment_settings": payment_settings,
        "order": {
            "status": "pending",
            "subtotal": {"value": valor_centavos, "offset": 100},
            "tax": {"value": 0, "offset": 100},
            "shipping": {"value": 0, "offset": 100},
            "discount": {"value": 0, "offset": 100},
            "items": [
                {
                    "retailer_id": "fatura-internet",
                    "name": item_name,
                    "amount": {"value": valor_centavos, "offset": 100},
                    "quantity": 1,
                }
            ],
        },
    }


def _build_template_payload(
    *,
    to: str,
    template_name: str,
    template_language: str,
    template_def: Dict[str, Any],
    media_id: Optional[str],
    customer_name: str,
    valor_br: str,
    vencimento_br: str,
    pix_code: str,
    linha_digitavel: str,
    fatura_desc: str,
    valor_centavos: int,
    merchant_name: str,
    payment_id: str,
    invoice_number: str,
) -> Dict[str, Any]:
    """
    Monta o payload conforme a estrutura real do template na Meta.
    Nome do cliente: sempre customer_name (Asaas).
    """
    components: List[Dict] = []

    header_fmt = _template_header_format(template_def)
    if header_fmt == "DOCUMENT" and media_id:
        components.append({
            "type": "header",
            "parameters": [
                {
                    "type": "document",
                    "document": {
                        "id": media_id,
                        "filename": "fatura.pdf",
                    },
                }
            ],
        })
    elif header_fmt == "DOCUMENT" and not media_id:
        logger.warning(
            "[BillingSend] Template %s exige header DOCUMENT mas PDF não disponível.",
            template_name,
        )

    body_params = _build_body_parameters(
        template_def,
        customer_name=customer_name,
        valor_br=valor_br,
        vencimento_br=vencimento_br,
        merchant_name=merchant_name,
        fatura_desc=fatura_desc,
    )
    if body_params:
        components.append({"type": "body", "parameters": body_params})

    od_index = _order_details_button_index(template_def)
    if od_index is not None and pix_code:
        order_details = _build_order_details(
            pix_code=pix_code,
            linha_digitavel=linha_digitavel,
            fatura_desc=fatura_desc,
            valor_centavos=valor_centavos,
            merchant_name=merchant_name,
            payment_id=payment_id,
            invoice_number=invoice_number,
        )
        components.append({
            "type": "button",
            "sub_type": "order_details",
            "index": od_index,
            "parameters": [
                {"type": "action", "action": {"order_details": order_details}}
            ],
        })

    return {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": template_language},
            "components": components,
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Passo 4: Enviar mensagem via API Meta
# ──────────────────────────────────────────────────────────────────────────────
def _send_whatsapp_template(phone_number_id: str, token: str, payload: Dict) -> Tuple[bool, str]:
    """
    Envia o payload de template para a API da Meta.
    Retorna (success, error_message).
    """
    url = f"{GRAPH_BASE}/{phone_number_id}/messages"
    print(f"[Debug] Enviando para Meta: {json.dumps(payload, indent=2)}")
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=30,
        )
        data = resp.json() if resp.content else {}
        if resp.status_code == 200 and data.get("messages"):
            return True, ""
        err = data.get("error", {}).get("message") or str(data)
        logger.warning("[BillingSend] Falha ao enviar template: %s | %s", resp.status_code, err)
        return False, err
    except Exception as exc:
        logger.error("[BillingSend] Exceção ao enviar: %s", exc)
        return False, str(exc)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers: PDF e PIX do Asaas
# ──────────────────────────────────────────────────────────────────────────────
def _resolve_pdf_url(payment: Dict) -> str:
    """Tenta obter URL de PDF pública do pagamento Asaas."""
    for key in ("bankSlipUrl", "invoiceUrl"):
        url = (payment.get(key) or "").strip()
        if url.lower().startswith("https://"):
            return url
    return ""



# ──────────────────────────────────────────────────────────────────────────────
# Offsets e agendamento (mesmo padrão do billing_reminder_service do provedor)
# ──────────────────────────────────────────────────────────────────────────────
def _parse_due_offsets(raw: str) -> List[int]:
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            continue
    return out


def _effective_offsets(config) -> List[int]:
    return _parse_due_offsets(getattr(config, "billing_reminder_due_offsets", None) or "")


def _billing_config_weekday(now) -> str:
    """Dias da config UI: 0=domingo … 6=sábado (Python weekday: seg=0 … dom=6)."""
    return str((now.weekday() + 1) % 7)


def _in_run_window(now, run_time: str, window_min: int) -> bool:
    parts = (run_time or "09:00").split(":")
    try:
        h = int(parts[0]) % 24
        m = int(parts[1]) % 60 if len(parts) > 1 else 0
    except (ValueError, IndexError):
        h, m = 9, 0
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
    w = max(0, min(int(window_min or 0), 45))
    if w == 0:
        return now.hour == h and now.minute == m
    return slot <= now < slot + timedelta(minutes=w)


def _filter_overdue(items: List[Dict], today: date, offsets: List[int]) -> List[Dict]:
    positive = {u for u in offsets if u >= 0}
    if not positive:
        return list(items)
    out = []
    for p in items:
        raw = (p.get("dueDate") or "")[:10]
        try:
            dd = date.fromisoformat(raw)
        except ValueError:
            continue
        delta = (today - dd).days
        if delta >= 0 and delta in positive:
            out.append(p)
    return out


def _pending_for_offsets(asaas, today: date, offsets: List[int]) -> List[Dict]:
    non_pos = sorted({u for u in offsets if u <= 0})
    if not non_pos:
        return []
    targets = {today - timedelta(days=u) for u in non_pos}
    d_min = min(targets)
    d_max = max(targets)
    res = asaas.list_payments(
        status="PENDING",
        due_date_ge=d_min.isoformat(),
        due_date_le=d_max.isoformat(),
    )
    if not res.get("success"):
        return []
    out = []
    for p in res.get("data", []) or []:
        raw = (p.get("dueDate") or "")[:10]
        try:
            dd = date.fromisoformat(raw)
        except ValueError:
            continue
        if dd in targets:
            out.append(p)
    return asaas.confirm_payments(out, max_items=100)


def _calc_offset(payment: Dict, today_d: date) -> int:
    """Retorna quantos dias de diferença entre hoje e o vencimento."""
    due_str = payment.get("dueDate") or ""
    if not due_str:
        return 0
    try:
        due_d = date.fromisoformat(due_str)
        return (today_d - due_d).days
    except (ValueError, TypeError):
        return 0


def _get_linha_digitavel(asaas, payment_id: str) -> str:
    try:
        res = asaas.get_payment_identification_field(payment_id)
        if res.get("success"):
            d = res.get("data") or {}
            return (d.get("identificationField") or "").strip()
    except Exception:
        pass
    return ""


# ──────────────────────────────────────────────────────────────────────────────
# Função principal: executar ciclo de envio
# ──────────────────────────────────────────────────────────────────────────────
def run_billing_send_cycle(force: bool = False) -> Dict:
    """
    Executa um ciclo de envio de cobranças usando o canal WhatsApp do Superadmin.

    Busca faturas no Asaas, mas só envia se estiver dentro da janela de horário
    e dias configurados no Superadmin, a menos que force=True.
    """
    # Imports locais para evitar circularidade
    from integrations.asaas_service import AsaasService
    from super_core.models import SystemConfig

    config_obj = SystemConfig.objects.first()
    if not config_obj:
        return {"success": False, "reason": "system_config_not_found"}

    payload = config_obj.payload or {}

    if not payload.get("billing_channel_enabled") and not force:
        return {"success": True, "reason": "billing_channel_disabled"}

    token         = (payload.get("billing_whatsapp_token") or "").strip()
    phone_num_id  = (payload.get("billing_whatsapp_phone_number_id") or "").strip()
    waba_id       = (payload.get("billing_whatsapp_waba_id") or "").strip()
    tpl_lang      = (payload.get("billing_whatsapp_template_language") or "pt_BR").strip()

    if not token or not phone_num_id:
        return {"success": False, "reason": "billing_whatsapp_not_configured"}
    if not waba_id:
        return {"success": False, "reason": "billing_whatsapp_waba_id_missing"}

    now = timezone.localtime()

    if not force:
        # ── Verificar se hoje é dia de rodar ─────────────────────────────────────
        run_days_raw = str(payload.get("billing_run_days") or "0,1,2,3,4,5,6").strip()
        allowed_days = {d.strip() for d in run_days_raw.split(",") if d.strip()}
        if _billing_config_weekday(now) not in allowed_days:
            return {"success": True, "executed": False, "reason": "not_scheduled_day"}

        # ── Verificar se está no horário de rodar ────────────────────────────────
        run_time = str(payload.get("billing_run_time") or "09:00").strip()
        window_m = int(payload.get("billing_run_window_minutes") or 0)
        if not _in_run_window(now, run_time, window_m):
            return {"success": True, "executed": False, "reason": "not_scheduled_time"}

        # ── Deduplicação diária (garante que só roda uma vez por dia no horário) ──
        hm_label = run_time.replace(":", "")[:4]
        dedupe_key = f"billing_send_cycle:{now.strftime('%Y%m%d')}:{hm_label}"
        if not cache.add(dedupe_key, "1", timeout=26 * 3600):
            return {"success": True, "executed": False, "reason": "already_executed_today"}

    # ── Buscar faturas Asaas + Inter ────────────────────────────────────────
    asaas = AsaasService()
    asaas_ready = bool(asaas.access_token)
    if not asaas_ready:
        logger.warning("[BillingSend] Token do Asaas não configurado — só enviará cobranças Inter, se houver.")

    # Determinar offsets (ex: -1 = um dia antes, 0 = dia do vencimento, 2 = dois dias atrasado)
    offsets = _parse_due_offsets(str(payload.get("billing_reminder_due_offsets") or ""))
    if not offsets:
        logger.warning("[BillingSend] Campo 'Em quais situações enviar a cobrança' vazio — nada a enviar.")

    today_d = now.date()

    overdue_items: List[Dict] = []
    due_soon_items: List[Dict] = []
    if asaas_ready:
        overdue_res = asaas.list_payments(status="OVERDUE")
        overdue_items = asaas.confirm_payments(
            overdue_res.get("data", []) if overdue_res.get("success") else [],
            max_items=100,
        )
        overdue_items = _filter_overdue(overdue_items, today_d, offsets)
        due_soon_items = _pending_for_offsets(asaas, today_d, offsets)

    inter_items = _inter_payments_for_offsets(today_d, offsets)

    all_items = [(p, _calc_offset(p, today_d)) for p in (overdue_items + due_soon_items + inter_items)]
    logger.info(
        "[BillingSend] offsets=%s asaas_overdue=%s asaas_due_soon=%s inter=%s total=%s",
        offsets,
        len(overdue_items),
        len(due_soon_items),
        len(inter_items),
        len(all_items),
    )

    if not all_items:
        return {"success": True, "sent_ok": 0, "total": 0, "reason": "no_payments_to_remind"}

    # Nome do sistema como merchant_name
    site_name = payload.get("site_name") or "Nio Hub"
    merchant_name = site_name[:60]

    sent_ok = 0
    sent_err = 0
    template_cache: Dict[Tuple[str, str], Optional[Dict[str, Any]]] = {}

    try:
        send_interval = max(0, min(int(payload.get("billing_send_interval_seconds") or 0), 300))
    except (TypeError, ValueError):
        send_interval = 0

    for payment, offset in all_items:
        # Escolher template baseado no offset (dias)
        # ≤ 0 → billing_whatsapp_template_name (A Vencer)
        # > 0 → billing_whatsapp_template_name_vencida (Vencida)
        tpl_name_avencer = payload.get("billing_whatsapp_template_name") or "prox_do_vencimento"
        tpl_name_vencida = payload.get("billing_whatsapp_template_name_vencida") or tpl_name_avencer

        tpl_name = tpl_name_vencida if offset > 0 else tpl_name_avencer

        cache_key = (tpl_name, tpl_lang)
        if cache_key not in template_cache:
            template_cache[cache_key] = _fetch_whatsapp_template(
                waba_id, token, tpl_name, tpl_lang
            )
        template_def = template_cache[cache_key]
        if not template_def:
            logger.warning(
                "[BillingSend] Template '%s' (%s) não encontrado na Meta — pulando fatura %s",
                tpl_name,
                tpl_lang,
                payment.get("id"),
            )
            sent_err += 1
            continue

        customer_id = payment.get("customer")
        is_inter = (payment.get("provider") or "") == "inter"

        if is_inter:
            provedor = Provedor.objects.filter(id=payment.get("provedor_id")).first()
            if not provedor:
                continue
            customer_name = (provedor.company or provedor.nome or "Cliente").strip()
            raw_phone = provedor.mobile_phone or provedor.phone
            customer_phone = _normalize_phone(raw_phone)
            if not customer_phone:
                continue
            pix_code = (payment.get("pixCopiaECola") or "").strip()
            linha_digitavel = (payment.get("linhaDigitavel") or "").strip()
            media_id = None
            try:
                from integrations.inter_service import InterService
                pdf_res = InterService().baixar_pdf(str(payment.get("id") or ""))
                if pdf_res.get("success") and pdf_res.get("content"):
                    media_id = _upload_pdf_bytes_to_meta(phone_num_id, token, pdf_res["content"])
            except Exception as exc:
                logger.warning("[BillingSend] PDF Inter falhou fatura=%s: %s", payment.get("id"), exc)
        else:
            if not customer_id:
                continue
            cust_res = asaas.get_customer(customer_id)
            if not cust_res.get("success"):
                continue
            customer = cust_res.get("data") or {}
            customer_name = (customer.get("name") or "Cliente").strip()
            raw_phone = customer.get("mobilePhone") or customer.get("phone")
            customer_phone = _normalize_phone(raw_phone)
            if not customer_phone:
                continue
            pix_code = ""
            linha_digitavel = ""
            info_res = asaas.get_payment_billing_info(str(payment.get("id") or ""))
            if info_res.get("success"):
                info_data = info_res.get("data") or {}
                pix_code = (info_data.get("pix", {}) or {}).get("payload") or ""
                linha_digitavel = (info_data.get("bankSlip", {}) or {}).get("identificationField") or ""
            pdf_url = _resolve_pdf_url(payment)
            media_id = _upload_pdf_to_meta(phone_num_id, token, pdf_url) if pdf_url else None

        payment_id = str(payment.get("id") or "")
        invoice_number = _invoice_number_from_payment(payment)
        due_raw = payment.get("dueDate") or ""
        valor_br = _fmt_valor_br(payment.get("value"))
        venc_br = _fmt_due_br(due_raw)
        val_cents = _valor_centavos(payment.get("value"))

        if not pix_code and not linha_digitavel:
            logger.warning("[BillingSend] Sem dados de pagamento (PIX/Boleto) para fatura %s", payment_id)
            continue

        # Payload do template (estrutura dinâmica conforme Meta)
        msg_payload = _build_template_payload(
            to=customer_phone,
            template_name=tpl_name,
            template_language=tpl_lang,
            template_def=template_def,
            media_id=media_id,
            customer_name=customer_name,
            valor_br=valor_br,
            vencimento_br=venc_br,
            pix_code=pix_code,
            linha_digitavel=linha_digitavel,
            fatura_desc=payment.get("description", ""),
            valor_centavos=val_cents,
            merchant_name=merchant_name,
            payment_id=payment_id,
            invoice_number=invoice_number,
        )

        # Enviar
        ok, err_msg = _send_whatsapp_template(phone_num_id, token, msg_payload)
        _log_billing_send(
            payment=payment,
            customer_id=str(customer_id or ""),
            phone=customer_phone,
            template_name=tpl_name,
            offset=offset,
            success=ok,
            error_message=err_msg or "",
        )
        if ok:
            sent_ok += 1
        else:
            sent_err += 1

        if send_interval > 0:
            logger.info(
                "[BillingSend] Aguardando %ss antes do próximo envio (fatura %s)",
                send_interval,
                payment_id,
            )
            time.sleep(send_interval)

    return {
        "success": True,
        "executed": True,
        "sent_ok": sent_ok,
        "sent_err": sent_err,
        "total": len(all_items),
    }

