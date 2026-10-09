"""Execução das campanhas de disparo (envio por canal, agendamento e retomada)."""
from __future__ import annotations

import logging
import mimetypes
import os
import re
import threading
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db import close_old_connections, transaction
from django.db.models import Q
from django.utils import timezone

from campaigns.models import Campaign, CampaignRecipient

logger = logging.getLogger(__name__)

CANAL_TIPOS = {
    'whatsapp_oficial': 'WhatsApp Oficial',
    'whatsapp_session': 'WhatsApp QR code',
    'whatsapp': 'WhatsApp QR code',
    'telegram': 'Telegram',
}
TEXTO_LIVRE_TIPOS = ('whatsapp_session', 'whatsapp', 'telegram')
INTERVALO_MAX = 300
RESERVA_SEGUNDOS = 120
MEDIA_ID_VALIDADE = timedelta(days=25)

_PLACEHOLDER_RE = re.compile(r'\{([^{}\s]{1,60})\}')
_TEMPLATE_VAR_RE = re.compile(r'\{\{\s*(\d+)\s*\}\}')


def fold_key(value: str) -> str:
    import unicodedata

    s = unicodedata.normalize('NFKD', str(value or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')


def recipient_values(r: CampaignRecipient) -> Dict[str, str]:
    nome = (r.nome or '').strip()
    values = {fold_key(k): str(v) for k, v in (r.dados or {}).items() if v not in (None, '')}
    values.update({
        'nome': nome,
        'primeiro_nome': nome.split(' ')[0] if nome else '',
        'telefone': r.telefone or '',
    })
    return values


def render(text: str, r: CampaignRecipient) -> str:
    values = recipient_values(r)

    def _sub(match):
        key = fold_key(match.group(1))
        return values[key] if key in values else match.group(0)

    return _PLACEHOLDER_RE.sub(_sub, text or '')


# ---------------------------------------------------------------------------
# Templates (WhatsApp Oficial)
# ---------------------------------------------------------------------------

def _component(template_def: Dict[str, Any], kind: str) -> Dict[str, Any]:
    for comp in (template_def or {}).get('components') or []:
        if str(comp.get('type', '')).upper() == kind:
            return comp
    return {}


def template_requirements(template_def: Dict[str, Any]) -> Dict[str, Any]:
    """O que o template exige para ser enviado (variáveis do corpo, cabeçalho, botões)."""
    body = _component(template_def, 'BODY')
    header = _component(template_def, 'HEADER')
    footer = _component(template_def, 'FOOTER')
    buttons = _component(template_def, 'BUTTONS').get('buttons') or []
    body_vars = sorted({int(n) for n in _TEMPLATE_VAR_RE.findall(body.get('text') or '')})
    header_format = str(header.get('format') or '').upper()
    dynamic_url_button = any(
        str(b.get('type', '')).upper() == 'URL' and _TEMPLATE_VAR_RE.search(b.get('url') or '')
        for b in buttons
    )
    order_details = any(str(b.get('type', '')).upper() == 'ORDER_DETAILS' for b in buttons)
    if order_details:
        motivo = 'Template de cobrança (Pix/boleto) exige os dados da fatura de cada cliente.'
    elif dynamic_url_button:
        motivo = 'Botão de link variável ainda não é suportado em campanhas.'
    else:
        motivo = ''
    return {
        'body_text': body.get('text') or '',
        'body_vars': len(body_vars),
        'header_format': header_format,
        'header_text': (header.get('text') or '') if header_format == 'TEXT' else '',
        'header_text_var': header_format == 'TEXT' and bool(_TEMPLATE_VAR_RE.search(header.get('text') or '')),
        'header_media': header_format in ('IMAGE', 'VIDEO', 'DOCUMENT'),
        'footer_text': footer.get('text') or '',
        'buttons': [{'type': str(b.get('type', '')).upper(), 'text': b.get('text') or ''} for b in buttons],
        'dynamic_url_button': dynamic_url_button,
        'order_details': order_details,
        'suportado': not motivo,
        'motivo': motivo,
    }


def _template_payload(c: Campaign, r: CampaignRecipient) -> Tuple[List[Dict[str, Any]], str]:
    req = template_requirements(c.template_def)
    components: List[Dict[str, Any]] = []
    if req['header_text_var']:
        components.append({
            'type': 'header',
            'parameters': [{'type': 'text', 'text': render(c.template_header_texto, r) or '-'}],
        })
    elif req['header_media'] and (c.template_header_media_id or c.template_header_url):
        kind = req['header_format'].lower()
        media = {'id': c.template_header_media_id} if c.template_header_media_id else {'link': c.template_header_url}
        if kind == 'document':
            nome = os.path.basename(c.template_header_arquivo.name) if c.template_header_arquivo else ''
            media['filename'] = nome or 'documento.pdf'
        components.append({'type': 'header', 'parameters': [{'type': kind, kind: media}]})

    variaveis = list(c.template_variaveis or [])
    params = [render(variaveis[i] if i < len(variaveis) else '', r).strip() or '-' for i in range(req['body_vars'])]
    if params:
        components.append({'type': 'body', 'parameters': [{'type': 'text', 'text': p} for p in params]})

    preview = _TEMPLATE_VAR_RE.sub(
        lambda m: params[int(m.group(1)) - 1] if 0 < int(m.group(1)) <= len(params) else m.group(0),
        req['body_text'],
    )
    return components, preview or f'[Template: {c.template_name}]'


# ---------------------------------------------------------------------------
# Envio por canal
# ---------------------------------------------------------------------------

def _uazapi_credentials(provedor) -> Tuple[str, str]:
    from integrations.models import WhatsAppIntegration

    token = url = ''
    integ = WhatsAppIntegration.objects.filter(provedor=provedor).first()
    if integ:
        token = integ.access_token or ''
        url = (integ.settings or {}).get('whatsapp_url') or ''
    extras = provedor.integracoes_externas or {}
    token = token or extras.get('whatsapp_token') or ''
    url = url or extras.get('whatsapp_url') or ''
    url = re.sub(r'/send/text/?$', '', url.strip())
    return url, token


def ensure_header_media(c: Campaign) -> Optional[str]:
    """Envia o arquivo do cabeçalho para a Meta (uma vez por campanha) e guarda o media_id.

    A Meta mantém o media_id por 30 dias; reenviamos quando passar de MEDIA_ID_VALIDADE.
    Retorna a mensagem de erro ou None.
    """
    from integrations.whatsapp_cloud_send import upload_media_to_whatsapp

    if c.canal is None or c.canal.tipo != 'whatsapp_oficial' or not c.template_header_arquivo:
        return None
    req = template_requirements(c.template_def)
    if not req['header_media']:
        return None
    if c.template_header_media_id and c.template_header_media_em and \
            timezone.now() - c.template_header_media_em < MEDIA_ID_VALIDADE:
        return None
    try:
        path = c.template_header_arquivo.path
    except (NotImplementedError, ValueError):
        return 'Arquivo do cabeçalho indisponível'
    if not os.path.exists(path):
        return 'Arquivo do cabeçalho não encontrado no servidor. Envie o arquivo de novo.'
    mime = mimetypes.guess_type(path)[0] or 'application/octet-stream'
    ok, result = upload_media_to_whatsapp(c.canal, path, req['header_format'].lower(), mime)
    if not ok or not result:
        return f'A Meta recusou o arquivo do cabeçalho: {result or "erro desconhecido"}'
    c.template_header_media_id, c.template_header_media_em = result, timezone.now()
    Campaign.objects.filter(pk=c.pk).update(
        template_header_media_id=c.template_header_media_id,
        template_header_media_em=c.template_header_media_em,
    )
    return None


def _send_oficial(c: Campaign, r: CampaignRecipient) -> Tuple[bool, str, str, str]:
    from integrations.whatsapp_cloud_send import send_template_message

    components, preview = _template_payload(c, r)
    ok, err, data = send_template_message(
        c.canal, r.telefone, c.template_name, c.template_language or 'pt_BR', components or None
    )
    wamid = ''
    if ok and isinstance(data, dict):
        wamid = ((data.get('messages') or [{}])[0] or {}).get('id') or ''
    return bool(ok), err or '', wamid, preview


def _send_uazapi(c: Campaign, r: CampaignRecipient) -> Tuple[bool, str, str, str]:
    from core.uazapi_client import UazapiClient

    text = render(c.mensagem, r)
    url, token = _uazapi_credentials(c.provedor)
    if not url or not token:
        return False, 'WhatsApp QR code sem URL/token configurados', '', text
    extras = c.canal.dados_extras or {}
    instance = extras.get('instance_id') or extras.get('instance') or None
    ok = UazapiClient(url, token).enviar_mensagem(r.telefone, text, instance_id=instance)
    return ok, '' if ok else 'O WhatsApp QR code recusou o envio', '', text


def _send_telegram(c: Campaign, r: CampaignRecipient) -> Tuple[bool, str, str, str]:
    from integrations.telegram_service import telegram_manager

    text = render(c.mensagem, r)
    try:
        chat_id = int(r.telegram_chat_id)
    except (TypeError, ValueError):
        return False, 'Contato sem conversa no Telegram', '', text
    service = telegram_manager.get_service(c.canal_id)
    if not service or not getattr(service, 'client', None):
        return False, 'Telegram desconectado', '', text
    ok = bool(service.run_coro(service.send_message(chat_id, text)))
    return ok, '' if ok else 'O Telegram recusou o envio', '', text


def _send(c: Campaign, r: CampaignRecipient) -> Tuple[bool, str, str, str]:
    tipo = c.canal.tipo
    if tipo == 'whatsapp_oficial':
        return _send_oficial(c, r)
    if tipo in ('whatsapp_session', 'whatsapp'):
        return _send_uazapi(c, r)
    if tipo == 'telegram':
        return _send_telegram(c, r)
    return False, f'Canal {tipo} não suporta campanhas', '', ''


def _contact_for(c: Campaign, r: CampaignRecipient):
    from conversations.models import Contact

    if r.contato_id:
        contact = Contact.objects.filter(pk=r.contato_id, provedor_id=c.provedor_id).first()
        if contact:
            return contact
    if not r.telefone:
        return None
    contact, _ = Contact.objects.get_or_create(
        phone=r.telefone,
        provedor_id=c.provedor_id,
        defaults={'name': (r.nome or f'Cliente {r.telefone[-8:]}')[:255]},
    )
    return contact


def _record_in_chat(c: Campaign, contact, content: str, wamid: str) -> None:
    """Grava o envio no histórico do contato sem abrir atendimento."""
    from conversations.inbound_routing import find_inbound_conversation
    from conversations.models import Conversation, Inbox, Message

    inbox = Inbox.objects.filter(provedor_id=c.provedor_id, channel_id=str(c.canal_id)).first()
    if inbox is None:
        inbox = Inbox.objects.create(
            provedor_id=c.provedor_id,
            channel_id=str(c.canal_id),
            name=f'{CANAL_TIPOS.get(c.canal.tipo, c.canal.tipo)} - {c.canal.nome or c.canal.phone_number or c.canal_id}',
            channel_type=c.canal.tipo,
        )
    conversation = find_inbound_conversation(contact, inbox)
    if conversation is None:
        conversation = Conversation.objects.create(contact=contact, inbox=inbox, status='closed')
    attrs = {'sent_via': 'campanha', 'campaign_id': c.id, 'last_status': 'accepted'}
    if c.canal.tipo == 'whatsapp_oficial':
        attrs.update({'is_template': True, 'template_name': c.template_name, 'template_language': c.template_language})
    Message.objects.create(
        conversation=conversation,
        content=content[:4096],
        message_type='text',
        is_from_customer=False,
        external_id=wamid or None,
        additional_attributes=attrs,
    )


def send_one(c: Campaign, r: CampaignRecipient) -> None:
    contact = _contact_for(c, r)
    if contact is not None and contact.bloqueado_disparos:
        r.status, r.erro = 'ignorado', 'Contato bloqueou o recebimento de disparos'
        r.save(update_fields=['status', 'erro'])
        return
    try:
        ok, err, wamid, content = _send(c, r)
    except Exception as exc:
        logger.exception('[Campanha %s] erro ao enviar para destinatário %s', c.id, r.id)
        ok, err, wamid, content = False, str(exc), '', ''
    r.status = 'enviado' if ok else 'falhou'
    r.erro = '' if ok else (err or 'Falha no envio')[:500]
    r.external_id = wamid or ''
    r.enviado_em = timezone.now() if ok else None
    if contact is not None and not r.contato_id:
        r.contato = contact
    r.save(update_fields=['status', 'erro', 'external_id', 'enviado_em', 'contato'])
    if ok and contact is not None:
        try:
            _record_in_chat(c, contact, content, wamid)
        except Exception:
            logger.exception('[Campanha %s] falha ao gravar envio no histórico', c.id)


# ---------------------------------------------------------------------------
# Execução em segundo plano
# ---------------------------------------------------------------------------

def _claim(campaign_id: int) -> bool:
    now = timezone.now()
    return bool(
        Campaign.objects.filter(pk=campaign_id, status='enviando')
        .filter(Q(reservada_ate__isnull=True) | Q(reservada_ate__lt=now))
        .update(reservada_ate=now + timedelta(seconds=RESERVA_SEGUNDOS))
    )


def _renew(campaign_id: int, interval: int) -> None:
    Campaign.objects.filter(pk=campaign_id).update(
        reservada_ate=timezone.now() + timedelta(seconds=RESERVA_SEGUNDOS + interval)
    )


def _already_sent(c: Campaign, r: CampaignRecipient) -> bool:
    """A mesma pessoa pode estar nos contatos do sistema e na lista importada."""
    if r.telegram_chat_id:
        same = Q(telegram_chat_id=r.telegram_chat_id)
    elif r.telefone:
        same = Q(telefone=r.telefone)
    else:
        return False
    return c.destinatarios.filter(same, status='enviado').exclude(pk=r.pk).exists()


def run_campaign(campaign_id: int) -> None:
    close_old_connections()
    if not _claim(campaign_id):
        return
    try:
        first = Campaign.objects.select_related('canal').filter(pk=campaign_id).first()
        media_error = ensure_header_media(first) if first else None
        if media_error:
            Campaign.objects.filter(pk=campaign_id, status='enviando').update(
                status='falhou', erro=media_error[:1000], concluida_em=timezone.now()
            )
            return
        while True:
            close_old_connections()
            c = Campaign.objects.select_related('canal', 'provedor').filter(pk=campaign_id).first()
            if c is None or c.status != 'enviando':
                return
            if c.canal is None or not c.canal.ativo:
                Campaign.objects.filter(pk=c.id).update(
                    status='falhou', erro='Canal removido ou inativo', concluida_em=timezone.now()
                )
                return
            r = c.destinatarios.filter(status='pendente').order_by('id').first()
            if r is None:
                Campaign.objects.filter(pk=c.id, status='enviando').update(
                    status='concluida', concluida_em=timezone.now()
                )
                return
            if _already_sent(c, r):
                CampaignRecipient.objects.filter(pk=r.pk).update(
                    status='ignorado', erro='Já recebeu por outra lista desta campanha'
                )
                continue
            interval = min(max(int(c.intervalo_segundos or 0), 0), INTERVALO_MAX)
            _renew(c.id, interval)
            send_one(c, r)
            if interval and c.destinatarios.filter(status='pendente').exists():
                for _ in range(interval):
                    time.sleep(1)
    except Exception as exc:
        logger.exception('[Campanha %s] execução interrompida', campaign_id)
        Campaign.objects.filter(pk=campaign_id, status='enviando').update(
            status='falhou', erro=str(exc)[:1000], concluida_em=timezone.now()
        )
    finally:
        Campaign.objects.filter(pk=campaign_id).update(reservada_ate=None)
        close_old_connections()


def start_in_background(campaign_id: int) -> None:
    threading.Thread(
        target=run_campaign, args=(campaign_id,), name=f'niochat-campanha-{campaign_id}', daemon=True
    ).start()


def start_after_commit(campaign_id: int) -> None:
    transaction.on_commit(lambda: start_in_background(campaign_id))


def tick_campaigns() -> int:
    """Chamado a cada minuto: inicia as agendadas vencidas e retoma as interrompidas."""
    now = timezone.now()
    Campaign.objects.filter(status='agendada', agendada_para__lte=now).update(
        status='enviando', iniciada_em=now
    )
    ids = list(
        Campaign.objects.filter(status='enviando')
        .filter(Q(reservada_ate__isnull=True) | Q(reservada_ate__lt=now))
        .values_list('id', flat=True)
    )
    for campaign_id in ids:
        start_in_background(campaign_id)
    return len(ids)


def channel_issue(canal) -> Optional[str]:
    """Motivo pelo qual o canal não pode disparar agora (None = pode)."""
    if canal is None:
        return 'Escolha um canal'
    if canal.tipo not in CANAL_TIPOS:
        return 'Este canal não permite campanhas'
    if not canal.ativo:
        return 'Canal inativo'
    if canal.tipo == 'whatsapp_oficial' and not (canal.token and canal.phone_number_id):
        return 'Canal WhatsApp Oficial sem token ou Phone Number ID'
    if canal.tipo in ('whatsapp_session', 'whatsapp'):
        url, token = _uazapi_credentials(canal.provedor)
        if not url or not token:
            return 'WhatsApp QR code sem URL/token configurados'
    return None
