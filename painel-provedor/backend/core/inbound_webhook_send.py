"""
Processa disparos do webhook inbound (SGP → Niohub) e envia template WhatsApp via Meta.
"""
import json
import logging
import os
import re
import tempfile
import unicodedata
import threading
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urljoin, urlparse

import requests
from django.utils import timezone

from core.external_webhook_dispatch import (
    _body_text_from_template,
    classify_meta_var_slot,
    extract_meta_var_indices,
    get_payload_sgp_value,
    resolve_merchant_display_name,
    template_has_document_header,
    template_has_order_details_button,
)

_META_VAR_IN_TEMPLATE = re.compile(r'\{\{(\d+)\}\}')
_SGP_PLACEHOLDER_RE = re.compile(r'\{[a-zA-Z0-9_]+\}')
_DATE_BR_RE = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')
_CONTENT_DISPOSITION_FILENAME_RE = re.compile(
    r'filename\*\s*=\s*(?:UTF-8\'\')?([^;]+)|filename\s*=\s*"([^"]+)"|filename\s*=\s*([^;\s]+)',
    re.I,
)
_MONEY_IN_TEXT_RE = re.compile(
    r'(?:R?\$?\s*)(\d{1,3}(?:\.\d{3})*,\d{2}|\d+\.\d{2}|\d+,\d{2})',
    re.I,
)

_SLOT_SGP_KEYS: Dict[str, Tuple[str, ...]] = {
    'name': ('cliente1', 'cliente', 'nome', 'nome_cliente'),
    # Datas: ordem depende do rótulo no template (original vs atualizado).
    'date_original': ('vencimento_original', 'data_vencimento_original', 'vencimento'),
    'date_updated': ('vencimento', 'data_vencimento_atualizada', 'vencimento_br', 'data_vencimento'),
    'date': ('vencimento', 'vencimento_original', 'data_aviso', 'data_vencimento'),
    'money': ('valor', 'valor_desc', 'valor_titulo'),
    'title': ('titulo', 'idcontrato', 'numero_titulo'),
    'provider': ('provedor', 'nome_provedor'),
}

_DATE_SLOTS = frozenset({'date', 'date_original', 'date_updated'})
from integrations.billing_reminder_service import (
    _normalize_phone,
    _send_whatsapp_text,
    send_cobranca_dispatch,
)
from integrations.whatsapp_cloud_send import (
    _extract_pix_info_from_code,
    upload_media_to_whatsapp,
)
from integrations.whatsapp_templates import list_message_templates

logger = logging.getLogger(__name__)

# SGP HTTP Genérico envia destino em `to`; demais integrações podem usar numero/celular.
_PHONE_KEYS = ('to', 'numero', 'celular', 'telefone', 'phone', 'number', 'destino', 'whatsapp')
def _normalize_valor_input(valor: Any) -> str:
    """Aceita só o número (50,00); remove 'valor de', 'R$', etc. se o SGP enviar texto extra."""
    text = str(valor or '').strip()
    if not text or '{' in text:
        return text
    m = re.search(r'(?:valor\s+de|no\s+valor\s+de)\s*([\d.,]+)', text, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r'[\d]+[.,][\d]{2}|[\d]+', text)
    return m.group(0) if m else text
def sgp_boleto_pdf_candidates(boleto_url: str) -> List[str]:
    """URLs possíveis para baixar o PDF do boleto SGP (/.pdf costuma 404)."""
    raw = (boleto_url or '').strip()
    if not raw.lower().startswith('https://'):
        return []
    base = raw.split('?', 1)[0].rstrip('/')
    seen: set[str] = set()
    out: List[str] = []
    for cand in (
        raw,
        base,
        f'{base}/',
        f'{base}.pdf',
        f'{base}/.pdf',
        f'{base}/pdf',
        f'{base}/download',
        f'{base}/boleto.pdf',
    ):
        if cand not in seen:
            seen.add(cand)
            out.append(cand)
    return out


def _pdf_from_html_page(html: bytes, page_url: str) -> Optional[str]:
    try:
        text = html.decode('utf-8', errors='ignore')
    except Exception:
        return None
    for match in re.finditer(r'''(?:href|src)=["']([^"']+\.pdf[^"']*)["\']''', text, re.I):
        href = match.group(1).strip()
        if href.startswith('http'):
            return href
        return urljoin(page_url, href)
    return None


def _ensure_pdf_filename(name: str) -> str:
    raw = re.sub(r'[\\/:*?"<>|]+', '_', (name or '').strip())
    raw = raw.strip('. ') or 'documento'
    if not raw.lower().endswith('.pdf'):
        raw = f'{raw}.pdf'
    return raw[:240]


def _filename_from_content_disposition(header: str) -> str:
    if not header:
        return ''
    m = _CONTENT_DISPOSITION_FILENAME_RE.search(header)
    if not m:
        return ''
    raw = (m.group(1) or m.group(2) or m.group(3) or '').strip().strip('"')
    if not raw:
        return ''
    return _ensure_pdf_filename(unquote(raw))


def resolve_document_filename_for_send(
    payload: Optional[Dict[str, Any]] = None,
    *,
    source_url: str = '',
    template_name: str = '',
    content_disposition: str = '',
) -> str:
    """
    Nome exibido no WhatsApp para o PDF do header.
    Não assume fatura: usa nome do payload, Content-Disposition, URL ou template.
    """
    payload = payload or {}
    for key in (
        'documento_nome',
        'nome_arquivo',
        'filename',
        'document_filename',
        'nome_documento',
        'arquivo_nome',
    ):
        val = _payload_direct(payload, key)
        if val:
            return _ensure_pdf_filename(str(val))

    from_cd = _filename_from_content_disposition(content_disposition)
    if from_cd:
        return from_cd

    path = urlparse(source_url or '').path or ''
    base = os.path.basename(path.rstrip('/'))
    if base.lower().endswith('.pdf') and len(base) > 4:
        return _ensure_pdf_filename(unquote(base))

    tn = (template_name or '').lower()
    url_l = f'{source_url or ""} {path}'.lower()
    blob = f'{tn} {url_l}'
    if any(x in blob for x in ('assinatura', 'assinado', 'contrato', 'adesao', 'termo')):
        if any(x in blob for x in ('assin', 'print')):
            return 'contrato_assinado.pdf'
        return 'contrato.pdf'
    if any(x in blob for x in ('fatura', 'cobranca', 'boleto', 'pagamento', 'invoice')):
        return 'fatura.pdf'
    return 'documento.pdf'


def _download_pdf_bytes(url: str) -> Tuple[Optional[bytes], Optional[str], str]:
    """Retorna (conteúdo, erro, nome_sugerido)."""
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=25,
            headers={'Accept': 'application/pdf,*/*'},
        )
        if resp.status_code >= 400:
            return None, f'HTTP {resp.status_code}', ''
        content = resp.content or b''
        ct = (resp.headers.get('Content-Type') or '').lower()
        suggested = _filename_from_content_disposition(
            resp.headers.get('Content-Disposition') or ''
        )
        if content.startswith(b'%PDF') or 'application/pdf' in ct:
            return content, None, suggested
        if 'text/html' in ct and content:
            nested = _pdf_from_html_page(content, resp.url or url)
            if nested and nested != url:
                return _download_pdf_bytes(nested)
        return None, 'não é PDF', ''
    except Exception as exc:
        return None, str(exc), ''


def upload_sgp_boleto_to_meta(
    canal, boleto_url: str
) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    Baixa PDF do SGP, upload Meta, retorna (media_id, pdf_url, erro, filename_sugerido).
    """
    last_err = 'Nenhuma URL de boleto retornou PDF.'
    for cand in sgp_boleto_pdf_candidates(boleto_url):
        content, err, suggested_name = _download_pdf_bytes(cand)
        if not content:
            last_err = f'{cand}: {err}'
            continue
        fd, path = tempfile.mkstemp(suffix='.pdf')
        try:
            os.write(fd, content)
            os.close(fd)
            ok, result = upload_media_to_whatsapp(canal, path, 'document', 'application/pdf')
            if ok and result:
                logger.info(
                    '[inbound-send] PDF SGP OK url=%s media_id=%s name=%s',
                    cand[:90],
                    result,
                    suggested_name or '(inferir)',
                )
                return str(result), cand, None, suggested_name or ''
            last_err = str(result or 'upload Meta falhou')
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
    logger.warning('[inbound-send] PDF SGP indisponível: %s', last_err)
    return None, None, last_err, ''


def _components_have_media_id_header(components: Optional[List[Dict[str, Any]]]) -> bool:
    for comp in components or []:
        if str(comp.get('type', '')).lower() != 'header':
            continue
        for param in comp.get('parameters') or []:
            if (param.get('document') or {}).get('id'):
                return True
    return False


def _try_parse_json_dict(raw: Any) -> Optional[Dict[str, Any]]:
    """Tenta parsear JSON do SGP (GET costuma vir URL-encoded ou com quebras de linha)."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or not text.startswith('{'):
        return None
    candidates = [text]
    decoded = unquote(text)
    if decoded != text:
        candidates.append(decoded)
        twice = unquote(decoded)
        if twice != decoded:
            candidates.append(twice)
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _decode_scraped_json_string(raw: str) -> str:
    """Decodifica string JSON capturada por regex (suporta \\n e aspas escapadas)."""
    if not raw:
        return ''
    try:
        return json.loads(f'"{raw}"')
    except json.JSONDecodeError:
        return (
            raw.replace('\\n', '\n')
            .replace('\\r', '\r')
            .replace('\\t', '\t')
            .replace('\\"', '"')
            .replace('\\\\', '\\')
        )


def _scrape_json_string_field(raw: str, field: str) -> Optional[str]:
    """
    Extrai valor string de um campo JSON quando json.loads falha (GET SGP com msg grande).
    """
    if not isinstance(raw, str) or not raw.strip():
        return None

    m = re.search(rf'"{re.escape(field)}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw, re.S)
    if m:
        val = _decode_scraped_json_string(m.group(1)).strip()
        if val:
            return val

    next_keys = '|'.join(
        re.escape(k)
        for k in (
            '_niohub_template', 'documento_url', 'codigo_pix', 'codigopix',
            'titulo', 'linhadigitavel', 'valor', 'template_name', 'canal_id',
            'link', 'link_cobranca', 'button_url', 'url_botao', 'validacao_id',
            'link_validacao',
        )
    )
    m = re.search(
        rf'"{re.escape(field)}"\s*:\s*"(.*?)"\s*,\s*"(?:{next_keys})"',
        raw,
        re.S,
    )
    if m:
        val = _decode_scraped_json_string(m.group(1)).strip()
        if val:
            return val
    return None


def _scrape_fields_from_raw_msg(raw: str) -> Dict[str, Any]:
    """
    Fallback quando json.loads falha no parâmetro msg (JSON grande na URL do SGP).
    Extrai _niohub_template e campos técnicos via regex.
    """
    if not isinstance(raw, str) or not raw.strip():
        return {}

    out: Dict[str, Any] = {}
    tmpl: Dict[str, Any] = {}

    m_name = re.search(r'"template_name"\s*:\s*"([^"\\]+)"', raw)
    if m_name:
        tmpl['template_name'] = m_name.group(1).strip()

    m_lang = re.search(r'"template_language"\s*:\s*"([^"\\]+)"', raw)
    if m_lang:
        tmpl['template_language'] = m_lang.group(1).strip()

    m_canal = re.search(r'"canal_id"\s*:\s*(\d+)', raw)
    if m_canal:
        tmpl['canal_id'] = int(m_canal.group(1))

    if tmpl:
        out['_niohub_template'] = tmpl
        for key, val in tmpl.items():
            if out.get(key) in (None, ''):
                out[key] = val

    for key in (
        'documento_url', 'codigo_pix', 'codigopix', 'titulo',
        'linhadigitavel', 'valor', 'link', 'link_cobranca',
        'button_url', 'url_botao', 'validacao_id', 'link_validacao',
    ):
        m = re.search(rf'"{re.escape(key)}"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
        if not m:
            continue
        try:
            val = json.loads(f'"{m.group(1)}"')
        except json.JSONDecodeError:
            val = m.group(1)
        if val and '{' not in str(val):
            target = 'codigo_pix' if key == 'codigopix' else key
            if out.get(target) in (None, ''):
                out[target] = val

    mensagem = _scrape_json_string_field(raw, 'mensagem')
    if mensagem and out.get('mensagem') in (None, ''):
        out['mensagem'] = mensagem

    return out


def merge_msg_field(payload: Dict[str, Any]) -> Dict[str, Any]:
    """SGP costuma enviar o JSON da cobrança no parâmetro `msg`."""
    msg = payload.get('msg')
    rest = {k: v for k, v in payload.items() if k != 'msg'}

    if isinstance(msg, str) and msg.strip():
        parsed = _try_parse_json_dict(msg)
        if isinstance(parsed, dict):
            # Campos de nível superior do SGP (to, canal_id, mensagem preenchida) complementam o JSON.
            merged = {**parsed, **rest}
            return merged

        scraped = _scrape_fields_from_raw_msg(msg)
        if scraped:
            merged = {**scraped, **rest}
            logger.info(
                '[inbound-send] msg JSON não parseável — campos extraídos por fallback: template=%s keys=%s',
                _resolve_template_name(merged),
                list(merged.keys())[:15],
            )
            return merged

        if 'mensagem' not in payload:
            return {**payload, 'mensagem': msg}

    return payload


def payload_expects_template(payload: Dict[str, Any]) -> bool:
    """True se o disparo SGP claramente pede template Meta (mesmo com parse parcial)."""
    if _resolve_template_name(payload):
        return True
    raw_msg = payload.get('msg')
    if isinstance(raw_msg, str):
        lowered = raw_msg.lower()
        if '_niohub_template' in lowered or '"template_name"' in lowered:
            return True
    return False


def extract_inbound_payload_from_query(query_params: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza query string GET do SGP (msg JSON + campos soltos)."""
    payload = dict(query_params or {})
    for json_key in ('msg', 'data', 'payload', 'mensagem_json', 'body', 'message'):
        raw = payload.get(json_key)
        parsed = _try_parse_json_dict(raw) if isinstance(raw, str) else None
        if isinstance(parsed, dict):
            rest = {k: v for k, v in payload.items() if k != json_key}
            payload = {**parsed, **rest}
            break

    if isinstance(payload.get('msg'), str) and payload.get('msg', '').strip().startswith('{'):
        if not _resolve_template_name(payload):
            scraped = _scrape_fields_from_raw_msg(payload['msg'])
            if scraped:
                payload = {**scraped, **payload}

    tmpl_raw = payload.get('_niohub_template')
    if isinstance(tmpl_raw, str) and tmpl_raw.strip():
        parsed_tmpl = _try_parse_json_dict(tmpl_raw) or _try_parse_json_dict(f'{{{tmpl_raw}}}')
        if isinstance(parsed_tmpl, dict):
            payload['_niohub_template'] = parsed_tmpl

    return payload


def normalize_inbound_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    payload = merge_msg_field(dict(raw or {}))

    tmpl = payload.get('_niohub_template')
    if isinstance(tmpl, str) and tmpl.strip():
        try:
            tmpl = json.loads(tmpl)
        except json.JSONDecodeError:
            tmpl = {}
    if isinstance(tmpl, dict):
        for key in ('template_name', 'template_language', 'canal_id'):
            if payload.get(key) in (None, '') and tmpl.get(key) not in (None, ''):
                payload[key] = tmpl[key]
        payload['_niohub_template'] = tmpl

    if not _payload_direct(payload, 'codigo_pix'):
        pix = _payload_direct(payload, 'codigopix')
        if pix:
            payload['codigo_pix'] = pix
    if not _payload_direct(payload, 'documento_url'):
        link_val = _payload_direct(payload, 'link', 'link_cobranca', 'link_pix_html')
        if link_val:
            payload['documento_url'] = link_val
    return payload


def normalize_phone_digits(phone: str) -> str:
    """E.164 só dígitos (ex.: 5563992484773 ou 12125551234) para banco e API Meta."""
    from core.phone_utils import normalize_whatsapp_phone
    return normalize_whatsapp_phone(phone)


def extract_recipient_phone(payload: Dict[str, Any]) -> Optional[str]:
    for key in _PHONE_KEYS:
        val = payload.get(key)
        if val is None:
            continue
        text = str(val).strip()
        if not text or '{' in text:
            continue
        digits = normalize_phone_digits(text)
        # Aceita DDI internacional (ex.: EUA 11 dígitos) e BR 12/13
        if len(digits) >= 10:
            return digits
    return None


def _extract_wamid(response_data: Any) -> Optional[str]:
    if not isinstance(response_data, dict):
        return None
    messages = response_data.get('messages') or []
    if messages and isinstance(messages[0], dict):
        return messages[0].get('id')
    return None


def persist_inbound_template_send(
    provedor,
    canal,
    phone_digits: str,
    template_name: str,
    template_language: str,
    template_def: Optional[Dict[str, Any]],
    payload: Dict[str, Any],
    wamid: Optional[str],
    send_channel: str = '',
    *,
    is_template: bool = True,
) -> Optional[int]:
    """Grava contato/conversa/mensagem para o webhook Meta atualizar status (sent/delivered/failed)."""
    from conversations.models import Contact, Conversation, Inbox, Message

    if not phone_digits:
        return None

    contact_name = (
        payload.get('nome')
        or payload.get('name')
        or f'Cliente {phone_digits[-8:]}'
    )
    contact_name = str(contact_name).strip()[:255] or f'Cliente {phone_digits[-8:]}'

    contact, _ = Contact.objects.get_or_create(
        phone=phone_digits,
        provedor=provedor,
        defaults={'name': contact_name},
    )
    if contact.bloqueado_disparos:
        logger.warning('[inbound-send] Contato %s com bloqueio de disparos', phone_digits)

    inbox, _ = Inbox.objects.get_or_create(
        provedor=provedor,
        channel_id=str(canal.id),
        defaults={
            'name': f'WhatsApp - {canal.nome or canal.phone_number}',
            'channel_type': 'whatsapp_oficial',
        },
    )

    from conversations.inbound_routing import find_inbound_conversation
    conversation = find_inbound_conversation(contact, inbox)
    if conversation is None:
        conversation = Conversation.objects.create(contact=contact, inbox=inbox, status='closed')

    body_tpl = _body_text_from_template(template_def) if template_def else ''
    if is_template:
        content = (payload.get('mensagem') or body_tpl or f'[Template: {template_name}]')[:4096]
    else:
        content = (payload.get('mensagem') or '')[:4096] or '[Mensagem webhook]'

    attrs = {
        'is_template': is_template,
        'sent_via': 'inbound_webhook',
        'sgp_dispatch': True,
        'documento_url': payload.get('documento_url'),
        'last_status': 'accepted',
        'send_channel': send_channel or '',
    }
    if is_template:
        attrs['template_name'] = template_name
        attrs['template_language'] = template_language

    message = Message.objects.create(
        conversation=conversation,
        content=content,
        message_type='text',
        is_from_customer=False,
        external_id=wamid,
        additional_attributes=attrs,
    )
    logger.info(
        '[inbound-send] Mensagem persistida id=%s conversation=%s wamid=%s',
        message.id,
        conversation.id,
        wamid,
    )
    return message.id


def _template_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    tmpl = payload.get('_niohub_template')
    return tmpl if isinstance(tmpl, dict) else {}


def _resolve_template_name(payload: Dict[str, Any]) -> str:
    meta = _template_meta(payload)
    return (payload.get('template_name') or meta.get('template_name') or '').strip()


def _resolve_template_language(payload: Dict[str, Any]) -> str:
    meta = _template_meta(payload)
    return (payload.get('template_language') or meta.get('template_language') or 'pt_BR').strip()


def _resolve_canal_id(payload: Dict[str, Any]) -> Optional[int]:
    meta = _template_meta(payload)
    raw = payload.get('canal_id') or meta.get('canal_id')
    if raw in (None, ''):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _extract_message_text(payload: Dict[str, Any]) -> str:
    """Texto livre do disparo (SGP ou outro sistema) sem template Meta."""
    for key in ('mensagem', 'message', 'text', 'body'):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    msg = payload.get('msg')
    if isinstance(msg, str) and msg.strip() and not msg.strip().startswith('{'):
        return msg.strip()
    return ''


def _resolve_whatsapp_canal(provedor, payload: Dict[str, Any]):
    """Canal WhatsApp Oficial: explícito no payload ou único ativo do provedor."""
    from core.models import Canal

    canal_id = _resolve_canal_id(payload)
    if canal_id:
        try:
            canal = Canal.objects.get(
                id=canal_id,
                tipo='whatsapp_oficial',
                provedor=provedor,
                ativo=True,
            )
            return canal, None
        except Canal.DoesNotExist:
            return None, (
                f'Canal WhatsApp {canal_id} não encontrado ou inativo para este provedor.'
            )

    canais = list(
        Canal.objects.filter(
            provedor=provedor,
            tipo='whatsapp_oficial',
            ativo=True,
        ).order_by('id')
    )
    if len(canais) == 1:
        return canais[0], None
    if not canais:
        return None, 'Nenhum canal WhatsApp Oficial ativo neste provedor.'
    return None, (
        'Informe canal_id no JSON ou na URL do webhook. '
        f'Este provedor possui {len(canais)} canais WhatsApp ativos.'
    )


def _schedule_persist_inbound_send(
    provedor,
    canal,
    phone_digits: str,
    payload: Dict[str, Any],
    wamid: Optional[str],
    send_channel: str,
    *,
    template_name: str = '',
    template_language: str = 'pt_BR',
    template_def: Optional[Dict[str, Any]] = None,
    is_template: bool = True,
) -> None:
    def _persist_async():
        try:
            persist_inbound_template_send(
                provedor=provedor,
                canal=canal,
                phone_digits=phone_digits,
                template_name=template_name,
                template_language=template_language,
                template_def=template_def,
                payload=payload,
                wamid=wamid,
                send_channel=send_channel,
                is_template=is_template,
            )
        except Exception as exc:
            logger.error('[inbound-send] persist async: %s', exc, exc_info=True)

    threading.Thread(target=_persist_async, daemon=True).start()


def _find_meta_template(canal, template_name: str, template_language: str) -> Optional[Dict[str, Any]]:
    ok, templates, err = list_message_templates(canal, limit=100)
    if not ok or not templates:
        logger.warning('[inbound-send] Falha ao listar templates: %s', err)
        return None
    for t in templates:
        if t.get('name') == template_name and (t.get('language') or 'pt_BR') == template_language:
            return t
    for t in templates:
        if t.get('name') == template_name:
            return t
    return None


def _parse_valor_centavos(valor: Any) -> int:
    if valor is None or valor == '':
        return 0
    text = _normalize_valor_input(valor).replace('R$', '').replace(' ', '')
    if ',' in text and '.' in text:
        text = text.replace('.', '').replace(',', '.')
    elif ',' in text:
        text = text.replace(',', '.')
    try:
        return int(Decimal(text) * 100)
    except (InvalidOperation, ValueError):
        return 0


def _format_valor_br(valor: Any) -> str:
    centavos = _parse_valor_centavos(valor)
    return f'{centavos / 100:.2f}'.replace('.', ',')


def _payload_direct(payload: Dict[str, Any], *keys: str) -> Any:
    """Lê campo do JSON do SGP (chave exata ou case-insensitive), sem aliases do Niohub."""
    if not payload:
        return None
    key_map = {str(k).lower(): k for k in payload.keys() if k is not None}
    for key in keys:
        if key in payload:
            val = payload.get(key)
        else:
            actual = key_map.get(str(key).lower())
            val = payload.get(actual) if actual is not None else None
        if val is not None and str(val).strip() and '{' not in str(val):
            return val
    return None


def _sanitize_cliente_name(name: str) -> str:
    """Remove repetição acidental (ex.: «VANDA DO VANDA DO») comum em disparos SGP."""
    s = re.sub(r'\s+', ' ', (name or '').strip()).strip(',').strip()
    s = s.strip('*').strip()
    if not s:
        return s
    dup = re.match(r'^(.+?)\s+\1$', s, re.I)
    if dup:
        return dup.group(1).strip()
    words = s.split()
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        if [w.lower() for w in words[:half]] == [w.lower() for w in words[half:]]:
            return ' '.join(words[:half])
    return s


def _extract_cliente_name_from_mensagem(mensagem: str) -> str:
    """
    Extrai o nome do cliente da mensagem já preenchida pelo SGP.
    Cobre «Olá, NOME.» e «Prezado (a) *NOME*.» (comum quando o BODY Meta é
    diferente do texto livre que o SGP monta).
    """
    msg = (mensagem or '').strip()
    if not msg:
        return ''
    for pat in (
        # Prezado (a) *NOME*. / Prezado(a) NOME.
        r'prezado\s*\(?\s*a?\s*\)?\s*[,:]?\s*\*?([^*\n]+?)\*?\s*[\.\n]',
        r'prezado\s*\(?\s*a?\s*\)?\s*[,:]?\s*\*?([^*\n,]+)',
        # Olá, NOME.
        r'ol[aá],\s*(.+?)(?:\s*,\s*n[aã]o|\s*\.\s|\s*\n|\s+voc[eê]|(?:\s*\.\s*)?esperamos)',
        r'ol[aá],\s*(.+?)\.\s*(?:\n|esperamos|ate\s+o\s+presente|voc[eê])',
        r'ol[aá],\s*(.+?)\s*,\s*',
        r'ol[aá]\s+(.+?)\s*\.',
        r'sr\(?a?\)?\s*(.+?)\.',
    ):
        m = re.search(pat, msg, re.I | re.S)
        if m:
            name = _sanitize_cliente_name(m.group(1))
            if name and '{' not in name and len(name) >= 2:
                return name
    return ''


def _payload_has_sgp_semantic_fields(payload: Dict[str, Any]) -> bool:
    return any(
        get_payload_sgp_value(payload, key) is not None
        for key in (
            'cliente', 'cliente1', 'vencimento', 'vencimento_original',
            'valor', 'valor_desc',
        )
    )


def _sanitize_name_params(
    template_body: str,
    indices: List[int],
    params: Dict[int, str],
) -> Dict[int, str]:
    out = dict(params)
    for n in indices:
        if _classify_template_var_slot(template_body, n) != 'name':
            continue
        val = (out.get(n) or '').strip()
        if val:
            out[n] = _sanitize_cliente_name(val)
    return out


def _mensagem_sem_placeholders_sgp(mensagem: str) -> bool:
    return bool((mensagem or '').strip()) and not _SGP_PLACEHOLDER_RE.search(mensagem)


def _strip_accents(text: str) -> str:
    nfd = unicodedata.normalize('NFD', text or '')
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


def _flex_static_pattern(text: str, *, punctuation_flexible: bool = False) -> str:
    """Trecho fixo do template: ignora acentos e diferenças de espaço (SGP vs Meta)."""
    plain = _strip_accents((text or '').replace('*', ''))
    tokens = re.findall(r'\S+', plain)
    if not tokens:
        return r'\s*'
    if punctuation_flexible:
        parts = [re.escape(tok) + r'[,.]?\s*' for tok in tokens]
        return r'\s*'.join(parts)
    return r'\s*'.join(re.escape(tok) for tok in tokens) + r'\s*'


def _line_context_before_var(template_body: str, var_index: int) -> str:
    """Texto na mesma linha imediatamente antes de {{n}} (evita confundir Valor com Vencimento da linha de cima)."""
    marker = f'{{{{{var_index}}}}}'
    pos = (template_body or '').find(marker)
    if pos < 0:
        return ''
    line_start = (template_body or '').rfind('\n', 0, pos)
    line_start = 0 if line_start < 0 else line_start + 1
    return _strip_accents(template_body[line_start:pos]).lower()


def _val_looks_like_date_br(val: str) -> bool:
    s = (val or '').strip()
    return bool(s) and bool(_DATE_BR_RE.fullmatch(s) or re.match(r'^\d{2}/\d{2}/\d{4}$', s))


def _val_looks_like_money_br(val: str) -> bool:
    s = (val or '').strip()
    if not s or _val_looks_like_date_br(s):
        return False
    if _MONEY_IN_TEXT_RE.search(s):
        return True
    try:
        return _parse_valor_centavos(s) > 0
    except Exception:
        return False


def _sgp_money_fallback(payload: Dict[str, Any], mensagem: str = '') -> str:
    for key in _SLOT_SGP_KEYS['money']:
        raw = get_payload_sgp_value(payload, key)
        if raw is not None:
            formatted = _format_valor_br(raw)
            if formatted and not _val_looks_like_date_br(formatted):
                return formatted
    for m in _MONEY_IN_TEXT_RE.finditer(mensagem or ''):
        chunk = m.group(1).strip()
        if chunk and not _val_looks_like_date_br(chunk):
            return chunk
    return ''


def _format_date_br(val: Any) -> str:
    s = str(val or '').strip()
    if _val_looks_like_date_br(s):
        return s
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        y, mo, d = m.groups()
        return f'{d}/{mo}/{y}'
    return s


def _extract_date_from_mensagem(mensagem: str) -> str:
    msg = (mensagem or '').strip()
    if not msg:
        return ''
    patterns = (
        r'(?<!original\s)vencimento\s*:?\s*(\d{2}/\d{2}/\d{4})',
        r'cuja\s+data\s+de\s+vencimento\s+[eé]\s+(\d{2}/\d{2}/\d{4})',
        r'com\s+vencimento\s+(\d{2}/\d{2}/\d{4})',
        r'data\s+de\s+vencimento\s+[eé]\s+(\d{2}/\d{2}/\d{4})',
        r'vencimento\s+(\d{2}/\d{2}/\d{4})',
        r'vence\s+hoje\s+(\d{2}/\d{2}/\d{4})',
        r'vence\s+em\s+(\d{2}/\d{2}/\d{4})',
        r'valido\s+para\s+pagamento\s+ate\s+(\d{2}/\d{2}/\d{4})',
        r'pagamento\s+ate\s+(\d{2}/\d{2}/\d{4})',
    )
    for pat in patterns:
        m = re.search(pat, msg, re.I)
        if m:
            return m.group(1).strip()
    return ''


def _sgp_date_fallback(
    payload: Dict[str, Any],
    mensagem: str = '',
    slot: str = 'date',
) -> str:
    keys = _SLOT_SGP_KEYS.get(slot) or _SLOT_SGP_KEYS['date']
    for key in keys:
        raw = get_payload_sgp_value(payload, key)
        if raw is not None:
            formatted = _format_date_br(raw)
            if _val_looks_like_date_br(formatted):
                return formatted
    return _extract_date_from_mensagem(mensagem)


def _fix_date_money_slot_swap(
    template_body: str,
    indices: List[int],
    params: Dict[int, str],
    payload: Dict[str, Any],
    mensagem: str,
) -> Dict[int, str]:
    """Corrige troca valor↔data entre slots {{n}} (ex.: vencimento 70,00 e valor 13/06/2026)."""
    out = dict(params)
    date_slots = [
        n for n in indices if _classify_template_var_slot(template_body, n) in _DATE_SLOTS
    ]
    money_slots = [n for n in indices if _classify_template_var_slot(template_body, n) == 'money']
    money_fb = _sgp_money_fallback(payload, mensagem)

    for n in date_slots:
        val = (out.get(n) or '').strip()
        slot = _classify_template_var_slot(template_body, n)
        date_fb = _sgp_date_fallback(payload, mensagem, slot=slot)
        if val and not _val_looks_like_date_br(val):
            if (_val_looks_like_money_br(val) or not val) and date_fb:
                out[n] = date_fb
            elif date_fb and _val_looks_like_money_br(val):
                out[n] = date_fb

    for n in money_slots:
        val = (out.get(n) or '').strip()
        if val and not _val_looks_like_money_br(val):
            if _val_looks_like_date_br(val) and money_fb:
                out[n] = money_fb

    for dn in date_slots:
        for mn in money_slots:
            dv = (out.get(dn) or '').strip()
            mv = (out.get(mn) or '').strip()
            if _val_looks_like_money_br(dv) and _val_looks_like_date_br(mv):
                out[dn], out[mn] = mv, dv
    return out


def _classify_template_var_slot(template_body: str, var_index: int) -> str:
    """Inferência do tipo de {{n}} pelo texto ao redor (delegado ao classificador compartilhado)."""
    return classify_meta_var_slot(template_body, var_index)


def _collect_semantic_pool(mensagem: str, payload: Dict[str, Any]) -> Dict[str, List[str]]:
    """Valores candidatos extraídos da mensagem preenchida e dos campos SGP do JSON."""
    pool: Dict[str, List[str]] = {
        'name': [],
        'date': [],
        'date_original': [],
        'date_updated': [],
        'money': [],
        'title': [],
        'provider': [],
        'generic': [],
    }

    def _add(slot: str, val: Any) -> None:
        s = str(val or '').strip()
        if not s or '{' in s:
            return
        if slot in _DATE_SLOTS:
            s = _format_date_br(s)
        if s not in pool[slot]:
            pool[slot].append(s)
        if slot in ('date_original', 'date_updated') and s not in pool['date']:
            pool['date'].append(s)

    msg = (mensagem or '').strip()
    if msg:
        for d in _DATE_BR_RE.findall(msg):
            _add('date', d)
        for m in _MONEY_IN_TEXT_RE.finditer(msg):
            _add('money', m.group(1).strip())
        name = _extract_cliente_name_from_mensagem(msg)
        if name:
            _add('name', name)

    for slot, keys in _SLOT_SGP_KEYS.items():
        for key in keys:
            val = get_payload_sgp_value(payload, key)
            if val is not None:
                if slot == 'money':
                    _add(slot, _format_valor_br(val))
                else:
                    _add(slot, val)

    titulo_url = _titulo_from_boleto_url(payload)
    if titulo_url:
        _add('title', titulo_url)

    return pool


def _merge_template_params(indices: List[int], *sources: Dict[int, str]) -> Dict[int, str]:
    out: Dict[int, str] = {n: '' for n in indices}
    for src in sources:
        if not src:
            continue
        for n in indices:
            v = (src.get(n) or '').strip()
            if v and not out.get(n):
                out[n] = v
    return out


def _pick_from_pool(slot: str, pool: Dict[str, List[str]], start_idx: int) -> Tuple[str, int]:
    """Escolhe candidato do pool compatível com o tipo (evita data no slot de valor)."""
    candidates = pool.get(slot) or pool.get('generic') or []
    for i in range(start_idx, len(candidates)):
        val = candidates[i].strip()
        if not val:
            continue
        if slot == 'money' and not _val_looks_like_money_br(val):
            continue
        if slot in _DATE_SLOTS and not _val_looks_like_date_br(val):
            continue
        return val, i + 1
    return '', start_idx


def _fill_params_from_semantic_pool(
    template_body: str,
    indices: List[int],
    partial: Dict[int, str],
    pool: Dict[str, List[str]],
) -> Dict[int, str]:
    """Completa {{n}} faltantes usando tipo inferido do template + pool SGP/mensagem."""
    out = dict(partial)
    counters: Dict[str, int] = {k: 0 for k in pool}

    for n in indices:
        if (out.get(n) or '').strip():
            continue
        slot = _classify_template_var_slot(template_body, n)
        idx = counters.get(slot, 0)
        val, next_idx = _pick_from_pool(slot, pool, idx)
        if val:
            out[n] = val
            counters[slot] = next_idx
            continue
        compatible_fallbacks = {
            'name': ('name',),
            'date': ('date',),
            'date_original': ('date_original', 'date'),
            'date_updated': ('date_updated', 'date'),
            'money': ('money',),
            'title': ('title',),
            'provider': ('provider',),
            'generic': ('generic', 'title'),
        }
        for fallback in compatible_fallbacks.get(slot, ('generic',)):
            fi = counters.get(fallback, 0)
            val_fb, next_fb = _pick_from_pool(fallback, pool, fi)
            if val_fb:
                out[n] = val_fb
                counters[fallback] = next_fb
                break

    return out


def _extract_params_from_sgp_semantic_fields(
    template_body: str,
    indices: List[int],
    payload: Dict[str, Any],
) -> Dict[int, str]:
    """Mapeia {{n}} para campos SGP pelo contexto do template (nunca por posição fixa)."""
    out: Dict[int, str] = {}
    used_values: set = set()
    for n in indices:
        slot = _classify_template_var_slot(template_body, n)

        # 1) var_N explícito no JSON (exportação / mapeamento do provedor)
        direct = _payload_direct(payload, f'var_{n}', str(n), f'param_{n}')
        if direct is not None:
            text = str(direct).strip()
            if slot == 'money':
                text = _format_valor_br(text)
            elif slot in _DATE_SLOTS:
                text = _format_date_br(text)
            elif slot == 'name':
                text = _sanitize_cliente_name(text)
            out[n] = text
            used_values.add(text.lower())
            continue

        # 2) Campos SGP semânticos (vencimento_original, valor, …)
        for key in _SLOT_SGP_KEYS.get(slot, ()):
            val = get_payload_sgp_value(payload, key)
            if val is None:
                continue
            if slot == 'money':
                text = _format_valor_br(val)
            elif slot in _DATE_SLOTS:
                text = _format_date_br(val)
            else:
                text = str(val).strip()
            if slot == 'name':
                text = _sanitize_cliente_name(text)
            # Evita repetir a mesma data em {{2}} e {{3}} quando há original + atualizado
            if slot in _DATE_SLOTS and text.lower() in used_values:
                continue
            out[n] = text
            used_values.add(text.lower())
            break

        # Sem chute por posição: se o texto não indica o tipo e não há var_N no JSON, fica vazio.
    return out


def _extract_params_from_payload_keys(
    indices: List[int],
    payload: Dict[str, Any],
) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for n in indices:
        for key in (str(n), f'var_{n}', f'param_{n}'):
            raw = _payload_direct(payload, key)
            if raw is not None:
                out[n] = str(raw).strip()
                break
    return out


def _extract_params_from_filled_mensagem(template_body: str, filled: str) -> Dict[int, str]:
    """Quando o SGP já substituiu variáveis, extrai valores para cada {{n}} do template Meta."""
    if not template_body or not filled:
        return {}

    filled_clean = filled.strip().replace('*', '')
    filled_norm = _strip_accents(filled_clean)

    pattern_parts: List[str] = []
    capture_indices: List[int] = []
    pos = 0
    for m in _META_VAR_IN_TEMPLATE.finditer(template_body):
        static = template_body[pos:m.start()]
        if static.strip():
            pattern_parts.append(_flex_static_pattern(static))
        pattern_parts.append(r'(.+?)')
        capture_indices.append(int(m.group(1)))
        pos = m.end()
    tail = template_body[pos:]
    if tail.strip():
        pattern_parts.append(_flex_static_pattern(tail))
    if not capture_indices:
        return {}

    regex = '(?is)^' + ''.join(pattern_parts) + '$'
    match = re.match(regex, filled_norm)
    if not match:
        return {}

    out: Dict[int, str] = {}
    for i, n in enumerate(capture_indices):
        out[n] = match.group(i + 1).strip()
    return out


def _extract_params_fuzzy_structural(template_body: str, filled: str) -> Dict[int, str]:
    """Igual ao estrutural, mas tolera vírgula/ponto extras entre trechos fixos (templates customizados)."""
    if not template_body or not filled:
        return {}

    filled_norm = _strip_accents(filled.strip().replace('*', ''))
    pattern_parts: List[str] = []
    capture_indices: List[int] = []
    pos = 0
    for m in _META_VAR_IN_TEMPLATE.finditer(template_body):
        static = template_body[pos:m.start()]
        if static.strip():
            pattern_parts.append(_flex_static_pattern(static, punctuation_flexible=True))
        pattern_parts.append(r'(.+?)')
        capture_indices.append(int(m.group(1)))
        pos = m.end()
    tail = template_body[pos:]
    if tail.strip():
        pattern_parts.append(_flex_static_pattern(tail, punctuation_flexible=True))
    if not capture_indices:
        return {}

    regex = '(?is)^' + ''.join(pattern_parts) + '$'
    match = re.match(regex, filled_norm)
    if not match:
        return {}

    return {
        n: match.group(i + 1).strip()
        for i, n in enumerate(capture_indices)
    }


def _extract_params_label_guided(template_body: str, mensagem: str) -> Dict[int, str]:
    """Extrai valores pelos rótulos do template (Contrato, Valor, Vencimento…) na mensagem preenchida do SGP."""
    msg = (mensagem or '').strip().replace('*', '')
    if not msg:
        return {}

    out: Dict[int, str] = {}
    for m in _META_VAR_IN_TEMPLATE.finditer(template_body):
        n = int(m.group(1))
        # Usar só o rótulo na mesma linha (evita «Valor original» da linha de cima
        # ser associado ao {{3}} de «Vencimento»).
        label_ctx = _line_context_before_var(template_body, n)
        val = None
        if re.search(r'contrato\s*:', label_ctx):
            m2 = re.search(r'contrato\s*:?\s*([^\n]+)', msg, re.I)
            if m2:
                val = m2.group(1).strip()
        elif re.search(r'valor\s+original', label_ctx):
            m2 = re.search(
                r'valor\s+original\s*:?\s*R?\$?\s*([^\n]+)',
                msg,
                re.I,
            )
            if m2:
                val = m2.group(1).strip()
        elif re.search(r'vencimento\s+original', label_ctx):
            m2 = re.search(r'vencimento\s+original\s*:?\s*([^\n]+)', msg, re.I)
            if m2:
                val = m2.group(1).strip()
        elif re.search(r'(?<!original\s)vencimento\s*:', label_ctx):
            m2 = re.search(r'(?<!original\s)vencimento\s*:?\s*([^\n]+)', msg, re.I)
            if m2:
                val = m2.group(1).strip()
                if _val_looks_like_money_br(val) and not _val_looks_like_date_br(val):
                    val = _extract_date_from_mensagem(msg) or None
        elif re.search(r'com\s+vencimento|cuja\s+data\s+de\s+vencimento', label_ctx):
            m2 = re.search(
                r'(?:cuja\s+data\s+de\s+vencimento|com\s+vencimento|data\s+de\s+vencimento)\s+[eé]?\s*(\d{2}/\d{2}/\d{4})',
                msg,
                re.I,
            )
            if not m2:
                val = _extract_date_from_mensagem(msg) or None
            else:
                val = m2.group(1).strip()
        elif re.search(r'valor\s*:|(?:e\s+)?valor\s+r\$|no\s+valor\s+de', label_ctx):
            m2 = re.search(
                r'(?:e\s+)?valor\s*:?\s*(?:de\s+)?R?\$?\s*([\d.,]+)'
                r'|no\s+valor\s+de\s+([\d.,]+)',
                msg,
                re.I,
            )
            if m2:
                val = (m2.group(1) or m2.group(2) or '').strip()
                if val and _val_looks_like_date_br(val):
                    val = None
        elif re.search(r'ol[aá]\s*,\s*$', label_ctx):
            m2 = re.search(
                r'ol[aá],\s*(.+?)(?:\s*,\s*n[aã]o|\s*\.\s|\s*\n)',
                msg,
                re.I | re.S,
            )
            if m2:
                val = m2.group(1).strip().strip(',').strip()
            else:
                # Template Meta «Olá, {{1}}» + mensagem SGP «Prezado (a) *NOME*»
                val = _extract_cliente_name_from_mensagem(msg) or None
        elif re.search(r'prezado', label_ctx, re.I):
            m2 = re.search(r'prezado\s*\(?a?\)?\s*,?\s*\*?([^*\n,]+)', msg, re.I)
            if m2:
                val = m2.group(1).strip()
            else:
                val = _extract_cliente_name_from_mensagem(msg) or None
        elif re.search(r'vence em|vence hoje', label_ctx, re.I):
            m2 = re.search(
                r'(?:vence\s+em|vence\s+hoje)\s+(\d{2}/\d{2}/\d{4})',
                msg,
                re.I,
            )
            if m2:
                val = m2.group(1).strip()
        elif re.search(r'pagamento\s+ate|valido\s+para\s+pagamento', label_ctx, re.I):
            m2 = re.search(
                r'(?:pagamento\s+ate|valido\s+para\s+pagamento\s+ate)\s+(\d{2}/\d{2}/\d{4})',
                msg,
                re.I,
            )
            if m2:
                val = m2.group(1).strip()
            else:
                val = _extract_date_from_mensagem(msg) or None
        elif re.search(r'ol[aá]\s*,?\s*$', label_ctx) or (
            n == 1 and 'lembrete' in label_ctx
        ):
            m2 = re.search(r'ol[aá],?\s*([^\n,]+)', msg, re.I)
            if m2:
                val = m2.group(1).strip()
            else:
                val = _extract_cliente_name_from_mensagem(msg) or None
        elif n == 1 and _classify_template_var_slot(template_body, n) == 'name':
            val = _extract_cliente_name_from_mensagem(msg) or None
        elif re.search(r'equipe\s+d[ao]\s*$', label_ctx) or 'provedor' in label_ctx:
            m2 = re.search(
                r'equipe\s+d[ao]\s*([^\n]+?)(?:\s*$|\s+importante|\s+evite)',
                msg,
                re.I,
            )
            if m2:
                val = m2.group(1).strip()
        elif re.search(r'documento\s*:', label_ctx):
            m2 = re.search(r'documento\s*:?\s*([^\n]+)', msg, re.I)
            if m2:
                val = m2.group(1).strip()
        elif re.search(r'fatura\s*#?\s*:', label_ctx):
            m2 = re.search(r'fatura\s*#?\s*:?\s*([^\n]+)', msg, re.I)
            if m2:
                val = m2.group(1).strip()
        if val and '{' not in val:
            slot = _classify_template_var_slot(template_body, n)
            if slot == 'name':
                val = _sanitize_cliente_name(val)
            out[n] = val
    return out


def _extract_params_cobranca_sgp_heuristic(
    mensagem: str,
    indices: List[int],
    payload: Dict[str, Any],
    template_body: str = '',
) -> Dict[int, str]:
    """
    Padrões comuns de cobrança SGP quando a mensagem preenchida não casa 100% com o BODY Meta
    (ex.: «Olá, NOME , não detectamos… com vencimento DD/MM/AAAA e valor R$ X»).
    """
    msg = (mensagem or '').strip()
    if not msg or not indices:
        return {}

    name = _extract_cliente_name_from_mensagem(msg)
    if not name:
        for pat in (
            r'ol[aá],\s*(.+?)\s*,\s*n[aã]o\s+detectamos',
            r'ol[aá],\s*(.+?)\s*\.\s*(?:\n|esperamos|ate\s+o\s+presente|voc[eê])',
            r'ol[aá],\s*(.+?)\s*\.\s*(?:\n|voc[eê])',
            r'ol[aá],\s*(.+?)\s*,\s*',
            r'ol[aá]\s+(.+?)\s*,\s*n[aã]o\s+detectamos',
        ):
            m = re.search(pat, msg, re.I | re.S)
            if m:
                name = m.group(1).strip().strip(',').strip()
                if name and '{' not in name:
                    break
                name = ''

    date_val = ''
    for pat in (
        r'com\s+vencimento\s+(\d{2}/\d{2}/\d{4})',
        r'data\s+de\s+vencimento\s+[eé]\s+(\d{2}/\d{2}/\d{4})',
        r'venceu\s+no\s+dia\s+(\d{2}/\d{2}/\d{4})',
        r'vencimento\s+(\d{2}/\d{2}/\d{4})',
        r'vence\s+hoje\s+(\d{2}/\d{2}/\d{4})',
        r'vence\s+em\s+(\d{2}/\d{2}/\d{4})',
        r'pagamento\s+ate\s+(\d{2}/\d{2}/\d{4})',
    ):
        m = re.search(pat, msg, re.I)
        if m:
            date_val = m.group(1).strip()
            break

    valor_val = ''
    m_val = re.search(
        r'(?:e\s+)?valor\s+(?:de\s+)?R?\$?\s*([\d.,]+)|no\s+valor\s+de\s+([\d.,]+)',
        msg,
        re.I,
    )
    if m_val:
        valor_val = (m_val.group(1) or m_val.group(2) or '').strip()
    if not valor_val:
        raw = _payload_direct(payload, 'valor', 'valor_desc')
        if raw is not None:
            valor_val = _format_valor_br(raw)

    pool = _collect_semantic_pool(msg, payload)
    if name:
        pool['name'].insert(0, name)
    if date_val:
        pool['date'].insert(0, date_val)
    if valor_val:
        pool['money'].insert(0, valor_val)

    out: Dict[int, str] = {}
    counters: Dict[str, int] = {}
    for n in indices:
        slot = _classify_template_var_slot(template_body, n) if template_body else 'generic'
        vals = pool.get(slot) or []
        i = counters.get(slot, 0)
        if i < len(vals):
            out[n] = vals[i]
            counters[slot] = i + 1
            continue
        if not template_body and len(indices) == 3:
            for fallback, key in zip(indices, ('name', 'money', 'date')):
                if n != fallback:
                    continue
                vals_fb = pool.get(key) or []
                if vals_fb:
                    out[n] = vals_fb[0]
    if all(out.get(n) for n in indices):
        return out
    return {}


def _sanitize_template_body_params(
    template_body: str,
    indices: List[int],
    params: Dict[int, str],
    payload: Dict[str, Any],
) -> Dict[int, str]:
    """Corrige troca data↔valor quando a extração automática erra o tipo do slot."""
    mensagem = (payload.get('mensagem') or '').strip()
    out = dict(params)
    for n in indices:
        slot = _classify_template_var_slot(template_body, n)
        val = (out.get(n) or '').strip()
        if slot == 'money' and val and not _val_looks_like_money_br(val):
            fixed = _sgp_money_fallback(payload, mensagem)
            if fixed:
                out[n] = fixed
        elif slot in _DATE_SLOTS and val and not _val_looks_like_date_br(val):
            fixed = _sgp_date_fallback(payload, mensagem, slot=slot)
            if fixed:
                out[n] = _format_date_br(fixed)
        elif slot in _DATE_SLOTS and not val:
            fixed = _sgp_date_fallback(payload, mensagem, slot=slot)
            if fixed:
                out[n] = _format_date_br(fixed)
    return _fix_date_money_slot_swap(template_body, indices, out, payload, mensagem)


def _resolve_template_body_params(
    body_text: str,
    payload: Dict[str, Any],
) -> Dict[int, str]:
    """
    Monta parâmetros {{n}} para templates Meta customizados (qualquer texto aprovado na Meta).

    Prioridade: body_params explícito → campos SGP no JSON → extração da mensagem preenchida
    (rótulos, estrutural, fuzzy, heurística) → pool semântico (nome/data/valor) por contexto do template.
    """
    indices = extract_meta_var_indices(body_text)
    if not indices:
        return {}

    for list_key in ('body_params', 'parametros', 'params', 'variaveis'):
        raw = payload.get(list_key)
        # Aceita array OU string com separador | (formato exportado pelo Niohub
        # para evitar que o SGP quebre o JSON ao substituir variáveis standalone).
        if isinstance(raw, str) and '|' in raw:
            arr = [v.strip() for v in raw.split('|')]
        elif isinstance(raw, (list, tuple)):
            arr = list(raw)
        else:
            continue
        if not arr:
            continue
        out: Dict[int, str] = {}
        for i, n in enumerate(indices):
            if i >= len(arr):
                break
            v = str(arr[i] or '').strip()
            if v and '{' not in v:
                out[n] = v
        if len(out) == len(indices):
            logger.info(
                '[inbound-send] Parâmetros template via %s: %s',
                list_key,
                {n: out[n] for n in indices},
            )
            return _sanitize_template_body_params(body_text, indices, out, payload)

    mensagem = (payload.get('mensagem') or '').strip()

    # Campos estruturados do JSON SGP (cliente, vencimento, valor) têm prioridade sobre
    # regex na mensagem preenchida — evita trocar data↔valor em produção.
    structured_sources: List[Dict[int, str]] = []
    if _payload_has_sgp_semantic_fields(payload):
        structured_sources.append(
            _extract_params_from_sgp_semantic_fields(body_text, indices, payload)
        )
    structured_sources.append(_extract_params_from_payload_keys(indices, payload))

    # Ordem de prioridade: body_params explícito → JSON SGP → extração da mensagem preenchida.
    sources: List[Dict[int, str]] = list(structured_sources)

    if _mensagem_sem_placeholders_sgp(mensagem):
        sources.extend([
            _extract_params_label_guided(body_text, mensagem),
            _extract_params_from_filled_mensagem(body_text, mensagem),
            _extract_params_fuzzy_structural(body_text, mensagem),
            _extract_params_cobranca_sgp_heuristic(
                mensagem, indices, payload, body_text
            ),
        ])

    merged = _merge_template_params(indices, *sources)

    missing_after_msg = [n for n in indices if not (merged.get(n) or '').strip()]
    if missing_after_msg:
        pool = _collect_semantic_pool(mensagem, payload)
        merged = _fill_params_from_semantic_pool(body_text, indices, merged, pool)

    final = _sanitize_template_body_params(body_text, indices, merged, payload)
    final = _sanitize_name_params(body_text, indices, final)

    if all((final.get(n) or '').strip() for n in indices):
        logger.info(
            '[inbound-send] Parâmetros template (mensagem/SGP) ordem=%s valores=%s',
            indices,
            {n: final[n] for n in indices},
        )
        return {n: final[n] for n in indices}

    missing = [n for n in indices if not (final.get(n) or '').strip()]
    logger.warning(
        '[inbound-send] Parâmetros template incompletos após extração: %s body_preview=%s',
        missing,
        (body_text or '')[:120],
    )
    return final


def _venc_br_to_iso(venc: str) -> str:
    v = (venc or '').strip()
    if len(v) >= 10 and v[2] == '/' and v[5] == '/':
        d, m, y = v[:10].split('/')
        return f'{y}-{m}-{d}'
    return v


def _clean_titulo_reference(raw: Any) -> str:
    """Número do título ({titulo}) — só dígitos, sem prefixo SGP."""
    s = str(raw or '').strip()
    if not s or s.lower() == 'sgp' or '{' in s:
        return ''
    if re.match(r'^SGP[-_]', s, re.I):
        s = re.sub(r'^SGP[-_]+', '', s, flags=re.I)
    digits = re.sub(r'\D', '', s)
    if digits:
        return digits[:80]
    return s[:80]


def _titulo_from_boleto_url(payload: Dict[str, Any]) -> str:
    """Extrai número do título da URL SGP (.../boleto/24507-TOKEN/)."""
    for url_key in ('documento_url', 'link', 'link_cobranca'):
        url = (payload.get(url_key) or '').strip()
        m = re.search(r'/boleto/(\d+)-', url, re.I)
        if m:
            return m.group(1)
    return ''


def _sgp_reference_id(payload: Dict[str, Any]) -> str:
    raw = _payload_direct(
        payload, 'titulo', 'titulo_doc', 'numero_titulo', 'num_titulo',
    )
    cleaned = _clean_titulo_reference(raw)
    if cleaned:
        return cleaned

    from_url = _titulo_from_boleto_url(payload)
    if from_url:
        return from_url

    logger.warning(
        '[inbound-send] reference_id sem titulo no disparo SGP — '
        'inclua o campo titulo no JSON ou URL do boleto em documento_url/link.'
    )
    return timezone.localtime().strftime('%Y%m%d%H%M%S')


def _sgp_linha_digitavel(payload: Dict[str, Any]) -> str:
    """Linha digitável enviada pelo SGP no JSON do disparo."""
    raw = _payload_direct(
        payload,
        'linhadigitavel',
        'linha_digitavel',
        'codigo_barras',
        'codigobarras',
        'linha_digitavel_boleto',
    )
    if raw in (None, ''):
        return ''
    digits = re.sub(r'\D', '', str(raw))
    if len(digits) >= 44:
        return digits[:48]
    logger.warning(
        '[inbound-send] linhadigitavel ignorada (precisa 44+ dígitos): len=%s valor=%s',
        len(digits),
        str(raw)[:40],
    )
    return ''


def _sgp_order_details_parameters(
    payload: Dict[str, Any],
    provedor,
    pix_code: str,
    template_def: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Monta order_details a partir dos campos enviados pelo SGP (sem inferência Niohub)."""
    valor_raw = _payload_direct(payload, 'valor', 'valor_desc') or '0'
    valor_centavos = _parse_valor_centavos(_normalize_valor_input(valor_raw))
    merchant = resolve_merchant_display_name(provedor, template_def)
    pix_key, pix_key_type = _extract_pix_info_from_code(pix_code)
    if not pix_key:
        pix_key = merchant[:77] if merchant else '00000000000'
        pix_key_type = pix_key_type or 'EVP'
    ref = _sgp_reference_id(payload)

    payment_settings: List[Dict[str, Any]] = [
        {
            'type': 'pix_dynamic_code',
            'pix_dynamic_code': {
                'code': pix_code,
                'merchant_name': merchant,
                'key': pix_key,
                'key_type': pix_key_type,
            },
        },
    ]
    linha = _sgp_linha_digitavel(payload)
    if linha:
        payment_settings.append({
            'type': 'boleto',
            'boleto': {'digitable_line': linha},
        })
        logger.info('[inbound-send] Boleto no order_details (linha digitável %s dígitos)', len(linha))
    else:
        logger.warning(
            '[inbound-send] Sem linhadigitavel no disparo — botão copiar boleto não será exibido. '
            'Inclua {linhadigitavel} no JSON da mensagem SGP.'
        )

    return {
        'reference_id': ref,
        'type': 'digital-goods',
        'payment_type': 'br',
        'currency': 'BRL',
        'total_amount': {'value': valor_centavos, 'offset': 100},
        'payment_settings': payment_settings,
        'order': {
            'status': 'pending',
            'subtotal': {'value': valor_centavos, 'offset': 100},
            'tax': {'value': 0, 'offset': 100},
            'shipping': {'value': 0, 'offset': 100},
            'discount': {'value': 0, 'offset': 100},
            'items': [
                {
                    'retailer_id': 'fatura-internet',
                    'name': 'Fatura Internet',
                    'amount': {'value': valor_centavos, 'offset': 100},
                    'quantity': 1,
                }
            ],
        },
    }


_URL_BUTTON_VAR_RE = re.compile(r'\{\{\s*1\s*\}\}')


def extract_url_button_param(value: str, template_button_url: str = '') -> str:
    """
    Extrai o texto que substitui {{1}} no botão URL dinâmico da Meta.

    - ID/sufixo puro (ex.: uuid ou uuid/print/assinado) → enviado como está
    - URL completa → remove a parte fixa do template (antes de {{1}}) e mantém o restante
      (pode ter vários segmentos de path)
    """
    raw = (value or '').strip()
    if not raw:
        return ''
    # Placeholder SGP não substituído — ignorar
    if '{' in raw and '}' in raw and not raw.lower().startswith('http'):
        return ''

    def _clean_suffix(s: str) -> str:
        s = (s or '').strip()
        if not s:
            return ''
        # Query da URL de origem não entra no {{1}} (salvo txt mode, aplicado depois)
        s = s.split('?', 1)[0]
        s = s.split('#', 1)[0]
        return s.strip('/')

    # Já é sufixo (com ou sem barras), sem scheme
    if '://' not in raw:
        return _clean_suffix(raw)

    template_url = (template_button_url or '').strip()
    static_prefix = ''
    if template_url and _URL_BUTTON_VAR_RE.search(template_url):
        static_prefix = _URL_BUTTON_VAR_RE.split(template_url, maxsplit=1)[0]

    try:
        full = raw
        # Se a URL completa começa com a parte fixa do template, o resto é o {{1}}
        if static_prefix:
            full_cmp = full
            pref_cmp = static_prefix
            # Comparação casefold no host/path costuma ser safe para este caso
            if full_cmp.lower().startswith(pref_cmp.lower()):
                return _clean_suffix(full_cmp[len(pref_cmp):])

            # Tenta pelo path: prefixo estático vs path da URL enviada
            pref_parsed = urlparse(static_prefix if '://' in static_prefix else f'https://x{static_prefix}')
            full_parsed = urlparse(full)
            pref_path = (pref_parsed.path or '').rstrip('/')
            full_path = (full_parsed.path or '').rstrip('/')
            same_host = (
                not pref_parsed.netloc
                or not full_parsed.netloc
                or pref_parsed.netloc.lower() == full_parsed.netloc.lower()
            )
            if same_host and pref_path and full_path.lower().startswith(pref_path.lower()):
                return _clean_suffix(full_path[len(pref_path):])

        # Sem match com o template: usa o path inteiro após o host (não só o último segmento)
        parsed = urlparse(full)
        path_suffix = _clean_suffix(parsed.path or '')
        if path_suffix:
            logger.warning(
                '[inbound-send] button_url não casa com a base do template (%s); '
                'usando path completo como {{1}}: %s',
                static_prefix or template_url or '(sem url)',
                path_suffix,
            )
            return path_suffix
    except Exception:
        return ''
    return ''


def build_template_components(
    template_def: Dict[str, Any],
    payload: Dict[str, Any],
    provedor,
    canal=None,
) -> Tuple[Optional[List[Dict[str, Any]]], Dict[str, Any]]:
    """
    Retorna (components, meta_extra) onde meta_extra pode conter avisos (ex.: PDF omitido).
    """
    components: List[Dict[str, Any]] = []
    meta_extra: Dict[str, Any] = {}
    body_text = _body_text_from_template(template_def)
    indices = extract_meta_var_indices(body_text)
    body_params = _resolve_template_body_params(body_text, payload)

    boleto_url = (_payload_direct(payload, 'documento_url', 'link', 'link_cobranca') or '').strip()
    if not boleto_url:
        # Alguns disparos (ex.: contrato assinado) mandam o PDF só em button_url
        button_as_doc = (
            _payload_direct(
                payload,
                'button_url', 'url_botao', 'documento', 'arquivo_url',
            ) or ''
        ).strip()
        if button_as_doc.lower().startswith('https://') and template_has_document_header(template_def):
            boleto_url = button_as_doc
    if boleto_url and not boleto_url.lower().startswith('https://'):
        raise ValueError('documento_url deve ser HTTPS.')
    pdf_source_url = ''
    template_name = (
        (payload.get('_niohub_template') or {}).get('template_name')
        or payload.get('template_name')
        or template_def.get('name')
        or ''
    )
    if template_has_document_header(template_def) and boleto_url and canal:
        media_id, pdf_source_url, upload_err, cd_name = upload_sgp_boleto_to_meta(canal, boleto_url)
        if media_id:
            doc_filename = cd_name or resolve_document_filename_for_send(
                payload,
                source_url=pdf_source_url or boleto_url,
                template_name=str(template_name),
            )
            meta_extra['pdf_media_id'] = media_id
            meta_extra['documento_url_meta'] = pdf_source_url
            meta_extra['document_filename'] = doc_filename
            components.append({
                'type': 'header',
                'parameters': [
                    {
                        'type': 'document',
                        'document': {
                            'id': media_id,
                            'filename': doc_filename,
                        },
                    }
                ],
            })
        else:
            logger.warning(
                '[inbound-send] Sem PDF para template (%s); usa interativo com PIX',
                upload_err,
            )

    # Botões URL (dinâmicos) — preencher {{1}} com ID/URL do disparo
    def _template_url_buttons() -> List[Dict[str, Any]]:
        out = []
        for comp in template_def.get('components') or []:
            if str(comp.get('type', '')).upper() != 'BUTTONS':
                continue
            for btn in comp.get('buttons') or []:
                if str(btn.get('type', '')).upper() != 'URL':
                    continue
                url = str(btn.get('url') or '')
                has_var = '{{1}}' in url or '{{ 1 }}' in url or bool(re.search(r'\{\{\s*1\s*\}\}', url))
                has_example = bool(btn.get('example'))
                if has_var or has_example:
                    out.append(btn)
        return out

    url_buttons = _template_url_buttons()
    if url_buttons:
        # Preferir button_url (validação/contato); fallback documento_url/link (recibo)
        button_src = (
            _payload_direct(
                payload,
                'button_url', 'url_botao', 'button_param', 'url_param',
                'validacao_id', 'link_validacao', 'id_validacao',
            )
            or boleto_url
            or ''
        ).strip()
        # Usa a URL do 1º botão dinâmico como base para calcular o sufixo de {{1}}
        template_btn_url = str(url_buttons[0].get('url') or '')
        rid = extract_url_button_param(button_src, template_btn_url)
        if rid:
            url_txt_mode = bool((payload.get('_niohub_template') or {}).get('url_txt_mode'))
            param = f'{rid}/?txt=1' if url_txt_mode else rid
            for idx, _btn in enumerate(url_buttons):
                # Cada botão pode ter base diferente — recalcula quando necessário
                btn_url = str(_btn.get('url') or template_btn_url)
                btn_param = (
                    extract_url_button_param(button_src, btn_url)
                    if btn_url != template_btn_url
                    else rid
                )
                if url_txt_mode and btn_param and not str(btn_param).endswith('txt=1'):
                    btn_param = f'{btn_param}/?txt=1'
                if not btn_param:
                    continue
                components.append({
                    'type': 'button',
                    'sub_type': 'url',
                    'index': idx,
                    'parameters': [{'type': 'text', 'text': btn_param}],
                })
        else:
            logger.warning(
                '[inbound-send] Template tem botão URL dinâmico, mas button_url/documento_url '
                'não veio no disparo — botão pode falhar na Meta'
            )

    if indices:
        params = []
        missing = []
        for n in indices:
            text = (body_params.get(n) or '').strip()
            if not text or '{' in text:
                missing.append(f'{{{{{n}}}}}')
            params.append({'type': 'text', 'text': text or '-'})
        if missing:
            raise ValueError(
                f'Parâmetros do template Meta não encontrados no disparo SGP: {", ".join(missing)}. '
                'Envie mensagem já preenchida (sem {{cliente}}), campos SGP no JSON (cliente, vencimento, valor, titulo) '
                'ou body_params na ordem das variáveis do template.'
            )
        components.append({'type': 'body', 'parameters': params})

    pix_code = (_payload_direct(payload, 'codigo_pix', 'codigopix') or '').strip()
    order_details = None
    if pix_code:
        order_details = _sgp_order_details_parameters(
            payload, provedor, pix_code, template_def=template_def
        )
        meta_extra['order_details'] = order_details
    if template_has_order_details_button(template_def) and order_details:
        components.append({
            'type': 'button',
            'sub_type': 'order_details',
            'index': 0,
            'parameters': [
                {'type': 'action', 'action': {'order_details': order_details}}
            ],
        })

    return (components if components else None), meta_extra


def process_inbound_plain_dispatch(
    provedor,
    payload: Dict[str, Any],
    phone: str,
    canal,
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Disparo sem template Meta: texto simples ou cobrança interativa (PIX/PDF) se enviados.
    """
    mensagem = _extract_message_text(payload)
    if not mensagem:
        return False, (
            'Texto da mensagem ausente. Envie mensagem, message, text ou body no payload.'
        ), {}

    if not canal.token or not canal.phone_number_id:
        return False, 'Canal sem token ou phone_number_id configurado.', {}

    phone_api = _normalize_phone(phone)
    pix_code = (_payload_direct(payload, 'codigo_pix', 'codigopix') or '').strip()
    send_meta: Dict[str, Any] = {'mode': 'plain'}

    logger.info(
        '[inbound-send] Disparo sem template canal=%s to=%s pix=%s',
        canal.id,
        phone_api,
        bool(pix_code),
    )

    if pix_code:
        order_details = _sgp_order_details_parameters(
            payload, provedor, pix_code,
        )
        send_meta['order_details'] = order_details
        boleto_url = (_payload_direct(payload, 'documento_url', 'link', 'link_cobranca') or '').strip()
        pdf_url = ''
        if boleto_url.lower().startswith('https://'):
            _, pdf_source, _, _ = upload_sgp_boleto_to_meta(canal, boleto_url)
            pdf_url = (pdf_source or '').strip()
        success, error_message, response_data, channel_used = send_cobranca_dispatch(
            canal,
            phone_api,
            '',
            '',
            None,
            interactive_body=mensagem,
            order_details_params=order_details,
            pdf_url=pdf_url,
            display_merchant=resolve_merchant_display_name(provedor),
            text_fallback=mensagem,
            document_filename=resolve_document_filename_for_send(
                payload,
                source_url=pdf_url or boleto_url,
                template_name=str(payload.get('template_name') or ''),
            ),
        )
    else:
        ok = _send_whatsapp_text(
            canal.phone_number_id,
            canal.token,
            phone_api,
            mensagem,
        )
        success = ok
        error_message = None if ok else 'Falha ao enviar mensagem de texto.'
        response_data = None
        channel_used = 'text' if ok else ''

    send_meta['send_channel'] = channel_used
    if not success:
        return False, error_message or 'Falha ao enviar mensagem WhatsApp.', send_meta

    wamid = _extract_wamid(response_data)
    send_meta['message_id'] = wamid

    _schedule_persist_inbound_send(
        provedor,
        canal,
        normalize_phone_digits(phone),
        payload,
        wamid,
        channel_used,
        is_template=False,
    )
    return True, None, send_meta


def _process_inbound_template_dispatch(
    provedor,
    payload: Dict[str, Any],
    phone: str,
    canal,
    template_name: str,
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Disparo com template Meta aprovado (cobrança com PIX/order_details quando aplicável)."""
    template_language = _resolve_template_language(payload)

    template_def = _find_meta_template(canal, template_name, template_language)
    if not template_def:
        return False, (
            f'Template Meta "{template_name}" ({template_language}) não encontrado no canal.'
        ), {}

    status = (template_def.get('status') or '').upper()
    if status and status not in ('APPROVED', 'ACTIVE', ''):
        return False, f'Template "{template_name}" não está aprovado (status: {status}).', {}

    try:
        components, build_meta = build_template_components(
            template_def, payload, provedor, canal=canal
        )
    except ValueError as e:
        return False, str(e), {}

    send_meta = dict(build_meta)
    order_details = build_meta.get('order_details')
    pix_code = (_payload_direct(payload, 'codigo_pix', 'codigopix') or '').strip()
    needs_order_details = template_has_order_details_button(template_def)
    if needs_order_details:
        if not pix_code:
            return False, 'codigo_pix ausente no disparo SGP.', send_meta
        if not order_details:
            return False, 'Não foi possível montar order_details (PIX).', send_meta

    pdf_url = (send_meta.get('documento_url_meta') or '').strip()
    mensagem = (payload.get('mensagem') or '').strip()
    phone_api = _normalize_phone(phone)

    body_tpl = _body_text_from_template(template_def)
    tpl_var_indices = extract_meta_var_indices(body_tpl)
    # Fallback de texto: templates estáticos (sem {{n}}) ou cobrança com order_details
    text_fallback = None
    if mensagem and (
        template_has_order_details_button(template_def)
        or not tpl_var_indices
        or '{{' not in mensagem
    ):
        text_fallback = mensagem

    has_media = _components_have_media_id_header(components)
    logger.info(
        '[inbound-send] Cobrança template=%s canal=%s to=%s media_id=%s static_body=%s',
        template_name,
        canal.id,
        phone_api,
        has_media,
        not tpl_var_indices,
    )

    success, error_message, response_data, channel_used = send_cobranca_dispatch(
        canal,
        phone_api,
        template_name,
        template_language,
        components,
        interactive_body=mensagem,
        order_details_params=order_details or {},
        pdf_url=pdf_url,
        display_merchant=resolve_merchant_display_name(provedor, template_def),
        text_fallback=text_fallback,
        document_filename=send_meta.get('document_filename') or resolve_document_filename_for_send(
            payload,
            source_url=pdf_url,
            template_name=template_name,
        ),
    )

    send_meta['send_channel'] = channel_used
    send_meta['mode'] = 'template'
    if not success:
        return False, error_message or 'Falha ao enviar cobrança WhatsApp.', send_meta

    wamid = _extract_wamid(response_data)
    send_meta['message_id'] = wamid
    send_meta['template_name'] = template_name

    _schedule_persist_inbound_send(
        provedor,
        canal,
        normalize_phone_digits(phone),
        payload,
        wamid,
        channel_used,
        template_name=template_name,
        template_language=template_language,
        template_def=template_def,
        is_template=True,
    )
    return True, None, send_meta


def process_inbound_webhook_dispatch(provedor, payload: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """
    Processa disparo do webhook inbound (SGP e outros).
    Com template_name → Meta template; sem template → texto ou interativo (PIX).
    Retorna (success, error_message, extra_info).
    """
    payload = normalize_inbound_payload(payload)

    phone = extract_recipient_phone(payload)
    if not phone:
        return False, (
            'Número do destinatário não informado. '
            'O SGP deve enviar o campo to (ex.: 63992484773) ou numero/celular na requisição.'
        ), {}

    from conversations.models import Contact

    if Contact.objects.filter(
        phone=phone, provedor=provedor, bloqueado_disparos=True
    ).exists():
        return False, f'O número {phone} está bloqueado para disparos no Niohub.', {}

    canal, canal_err = _resolve_whatsapp_canal(provedor, payload)
    if canal_err:
        return False, canal_err, {}

    if not canal.token or not canal.phone_number_id:
        return False, 'Canal sem token ou phone_number_id configurado.', {}

    template_name = _resolve_template_name(payload)
    if not template_name:
        if payload_expects_template(payload):
            return False, (
                'O JSON da mensagem SGP inclui _niohub_template, mas o Niohub não conseguiu '
                'interpretá-lo (comum em GET com JSON grande). Use POST com JSON no body ou '
                'confira o modelo de cobrança exportado em Integrações.'
            ), {}
        return process_inbound_plain_dispatch(provedor, payload, phone, canal)

    return _process_inbound_template_dispatch(
        provedor, payload, phone, canal, template_name
    )
