"""
Integração NioHub Calls (serviço Go whatsmeow + WebRTC).

Camada separada da API oficial Meta — só pareamento QR para voz.
Estado por canal em Canal.dados_extras['voice_calls'].
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode, urlparse

import qrcode
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

VOICE_CALLS_EXTRAS_KEY = 'voice_calls'


def voice_calls_configured() -> bool:
    return bool(getattr(settings, 'NIOHUB_CALLS_BASE_URL', '').strip())


def build_voice_calls_sse_url(client_id: str = 'web') -> Optional[str]:
    """
    URL SSE do serviço Go para o browser.
    Em dev (localhost) o front conecta direto; em produção use NIOHUB_CALLS_PUBLIC_EVENTS_URL.
    """
    if not voice_calls_configured():
        return None
    base = getattr(settings, 'NIOHUB_CALLS_BASE_URL', '').strip().rstrip('/')
    public = getattr(settings, 'NIOHUB_CALLS_PUBLIC_EVENTS_URL', '').strip().rstrip('/')
    effective = public or base
    if not public and '127.0.0.1' not in base and 'localhost' not in base:
        return None
    params: Dict[str, str] = {'clientId': (client_id or 'web').strip() or 'web'}
    key = getattr(settings, 'NIOHUB_CALLS_API_KEY', '').strip()
    if key:
        params['apiKey'] = key
    return f'{effective}/api/events?{urlencode(params)}'


def get_voice_calls_client():
    base = getattr(settings, 'NIOHUB_CALLS_BASE_URL', '').strip().rstrip('/')
    key = getattr(settings, 'NIOHUB_CALLS_API_KEY', '').strip()
    if not base:
        raise NioHubCallsNotConfigured('Serviço de ligações não configurado (NIOHUB_CALLS_BASE_URL).')
    return NioHubCallsClient(base, key)


def get_voice_calls_state(canal) -> Dict[str, Any]:
    extras = getattr(canal, 'dados_extras', None) or {}
    if not isinstance(extras, dict):
        return {}
    state = extras.get(VOICE_CALLS_EXTRAS_KEY)
    return dict(state) if isinstance(state, dict) else {}


def save_voice_calls_state(canal, state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    extras = dict(getattr(canal, 'dados_extras', None) or {})
    if state:
        state = {**state, 'updated_at': datetime.now(timezone.utc).isoformat()}
        extras[VOICE_CALLS_EXTRAS_KEY] = state
    else:
        extras.pop(VOICE_CALLS_EXTRAS_KEY, None)
    canal.dados_extras = extras
    canal.save(update_fields=['dados_extras', 'updated_at'])
    return get_voice_calls_state(canal)


def session_name_for_canal(canal) -> str:
    provedor_id = getattr(canal.provedor, 'id', 0) or 0
    return f'niohub-p{provedor_id}-c{canal.id}'


def normalize_session_status(raw: Any) -> str:
    text = str(raw or '').strip().lower()
    if text in ('connected', 'open', 'paired', 'active'):
        return 'connected'
    if text in ('pairing', 'qr', 'waiting', 'connecting'):
        return 'pairing'
    if text in ('disconnected', 'logged_out', 'closed'):
        return 'disconnected'
    return text or 'unknown'


def extract_pairing_code(payload: Any) -> Optional[str]:
    """Texto bruto do pareamento (URL wa.me ou payload whatsmeow) — não é imagem."""
    if not payload:
        return None
    if isinstance(payload, str):
        s = payload.strip()
        if not s or s.startswith('data:image'):
            return None
        return s
    if not isinstance(payload, dict):
        return None
    for key in ('qr', 'qrcode', 'qr_code', 'code'):
        val = payload.get(key)
        code = extract_pairing_code(val)
        if code:
            return code
    return None


def pairing_code_to_qr_image(code: Optional[str]) -> Optional[str]:
    """Converte código de pareamento em data URL PNG para o frontend."""
    if not code:
        return None
    s = code.strip()
    if s.startswith('data:image'):
        return s
    try:
        qr = qrcode.QRCode(version=1, box_size=6, border=2)
        qr.add_data(s)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
        return f'data:image/png;base64,{b64}'
    except Exception as exc:
        logger.warning('[NioHubCalls] falha ao gerar QR PNG: %s', exc)
        return None


def extract_qr_from_payload(payload: Any) -> Optional[str]:
    return pairing_code_to_qr_image(extract_pairing_code(payload))


def normalize_sdp_text(sdp: str) -> str:
    text = (sdp or '').replace('\r\n', '\n').replace('\r', '\n').strip()
    if not text:
        return ''
    if not text.endswith('\n'):
        text += '\n'
    return text.replace('\n', '\r\n')


def extract_sdp_offer(raw_data: Any, raw_body: Optional[bytes] = None) -> str:
    """Extrai SDP WebRTC do body JSON (DRF ou bytes brutos)."""
    def pick(val: Any) -> str:
        if val is None:
            return ''
        if isinstance(val, (list, tuple)):
            val = val[0] if val else ''
        if not isinstance(val, str):
            val = str(val)
        return val.strip()

    def from_mapping(data: Any) -> str:
        if not hasattr(data, 'get'):
            return ''
        for key in ('sdp_offer', 'sdp', 'sdpOffer', 'offer'):
            found = pick(data.get(key))
            if found:
                return normalize_sdp_text(found)
        return ''

    found = from_mapping(raw_data)
    if found:
        return found

    if raw_body:
        try:
            parsed = json.loads(raw_body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            parsed = None
        found = from_mapping(parsed)
        if found:
            return found
    return ''


def extract_sdp_from_request(request) -> str:
    """SDP a partir de request DRF/Django sem ler body após parse do DRF."""
    data = getattr(request, 'data', None)
    if data is not None:
        found = extract_sdp_offer(data)
        if found:
            return found
    try:
        body = request.body
    except Exception:
        body = None
    return extract_sdp_offer({}, body) if body else ''


def validate_sdp_offer(sdp: str) -> bool:
    return bool(sdp) and sdp.startswith('v=0') and 'm=audio' in sdp and len(sdp) >= 40


def parse_calls_error_message(text: str, status_code: int) -> str:
    if not text:
        return f'HTTP {status_code}'
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and obj.get('error'):
            return str(obj['error'])
    except json.JSONDecodeError:
        pass
    return text[:400]


class NioHubCallsNotConfigured(Exception):
    pass


class NioHubCallsError(Exception):
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class NioHubCallsClient:
    def __init__(self, base_url: str, api_key: str = ''):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key.strip()

    def _headers(self) -> Dict[str, str]:
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        return headers

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f'{self.base_url}{path}'
        timeout = kwargs.pop('timeout', 30)
        try:
            resp = requests.request(method, url, headers=self._headers(), timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            logger.warning('[NioHubCalls] %s %s falhou: %s', method, path, exc)
            raise NioHubCallsError(f'Não foi possível contactar o serviço de ligações: {exc}') from exc
        if resp.status_code >= 400:
            msg = parse_calls_error_message(resp.text or '', resp.status_code)
            raise NioHubCallsError(
                f'Serviço de ligações: {msg}',
                status_code=resp.status_code,
            )
        if not resp.text:
            return {}
        try:
            return resp.json()
        except json.JSONDecodeError:
            return {'raw': resp.text}

    def list_sessions(self) -> list:
        data = self._request('GET', '/api/sessions')
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ('sessions', 'data', 'items'):
                val = data.get(key)
                if isinstance(val, list):
                    return val
        return []

    def get_session(self, session_id: str) -> Dict[str, Any]:
        sid = str(session_id or '').strip()
        if not sid:
            return {}
        for item in self.list_sessions():
            if isinstance(item, dict) and str(item.get('id', '')) == sid:
                return item
        return {}

    def create_session(self, name: str) -> Dict[str, Any]:
        payload = {'name': name}
        return self._request('POST', '/api/sessions', json=payload)

    def set_session_webhook(self, session_id: str, webhook_url: str) -> None:
        """Registra URL de webhook na sessão (chamada para call.incoming/status/ended)."""
        if not session_id or not webhook_url:
            return
        try:
            self._request('POST', f'/api/sessions/{session_id}/webhook', json={'url': webhook_url})
        except Exception as exc:
            logger.warning('[NioHubCalls] set_session_webhook: %s', exc)

    def delete_session_webhook(self, session_id: str) -> None:
        try:
            self._request('DELETE', f'/api/sessions/{session_id}/webhook')
        except Exception:
            pass

    def delete_session(self, session_id: str) -> None:
        self._request('DELETE', f'/api/sessions/{session_id}')

    def pair_session(self, session_id: str) -> Dict[str, Any]:
        return self._request('POST', f'/api/sessions/{session_id}/pair', json={})

    def start_call(self, session_id: str, phone: str, duration_ms: int = 300000) -> Dict[str, Any]:
        return self._request(
            'POST',
            f'/api/sessions/{session_id}/calls',
            json={'phone': phone, 'duration_ms': duration_ms, 'record': False},
        )

    def send_webrtc_offer(self, session_id: str, call_id: str, sdp_offer: str) -> Dict[str, Any]:
        payload = json.dumps({'sdp_offer': sdp_offer}, ensure_ascii=False)
        return self._request(
            'POST',
            f'/api/sessions/{session_id}/calls/{call_id}/webrtc',
            data=payload.encode('utf-8'),
        )

    def accept_call(self, session_id: str, call_id: str) -> Dict[str, Any]:
        return self._request(
            'POST',
            f'/api/sessions/{session_id}/calls/{call_id}/accept',
            json={},
        )

    def reject_call(self, session_id: str, call_id: str) -> Dict[str, Any]:
        return self._request(
            'POST',
            f'/api/sessions/{session_id}/calls/{call_id}/reject',
            json={},
        )

    def end_call(self, session_id: str, call_id: str) -> None:
        self._request('DELETE', f'/api/sessions/{session_id}/calls/{call_id}')

    def iter_events(self, timeout: int = 300):
        params = {}
        if self.api_key:
            params['apiKey'] = self.api_key
        url = f'{self.base_url}/api/events'
        with requests.get(
            url,
            params=params,
            headers=self._headers(),
            stream=True,
            timeout=timeout,
        ) as resp:
            if resp.status_code >= 400:
                raise NioHubCallsError(f'SSE events HTTP {resp.status_code}', status_code=resp.status_code)
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith('data:'):
                    continue
                payload_text = raw_line[5:].strip()
                if payload_text in ('', '[DONE]'):
                    continue
                try:
                    yield json.loads(payload_text)
                except json.JSONDecodeError:
                    continue

    def find_session_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        for item in self.list_sessions():
            if not isinstance(item, dict):
                continue
            if (item.get('name') or item.get('id')) == name:
                return item
            if str(item.get('name', '')).strip() == name:
                return item
        return None

    def session_remote_status(self, session: Dict[str, Any]) -> str:
        if not session:
            return 'disconnected'
        if session.get('paired') is True or session.get('jid'):
            return 'connected'
        raw_state = str(session.get('state') or session.get('status') or '').lower()
        if raw_state == 'qr':
            return 'pairing'
        status = normalize_session_status(raw_state or session.get('connection'))
        if status == 'unknown' and session.get('connected') is True:
            return 'connected'
        return status

    def wait_for_pairing_code(self, session_id: str, timeout: int = 22) -> Optional[str]:
        """Escuta SSE (session-qr / auth-state) até obter o código de pareamento."""
        params = {}
        if self.api_key:
            params['apiKey'] = self.api_key
        url = f'{self.base_url}/api/events'
        target = str(session_id)
        try:
            with requests.get(
                url,
                params=params,
                headers=self._headers(),
                stream=True,
                timeout=timeout + 5,
            ) as resp:
                if resp.status_code >= 400:
                    return None
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if not raw_line or not raw_line.startswith('data:'):
                        continue
                    payload_text = raw_line[5:].strip()
                    if payload_text in ('', '[DONE]'):
                        continue
                    try:
                        payload = json.loads(payload_text)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    sid = payload.get('sessionId') or payload.get('session_id')
                    if sid and str(sid) != target:
                        continue
                    event_type = str(payload.get('type') or '').lower()
                    if event_type == 'auth-state':
                        if payload.get('paired') or str(payload.get('state', '')).lower() == 'open':
                            return None
                        code = extract_pairing_code(payload.get('qr'))
                        if code:
                            return code
                        continue
                    if event_type == 'session-qr':
                        code = extract_pairing_code(payload.get('qr'))
                        if code:
                            return code
        except requests.RequestException as exc:
            logger.debug('[NioHubCalls] SSE QR timeout/erro: %s', exc)
        return None

    def wait_for_qr(self, session_id: str, timeout: int = 22) -> Optional[str]:
        code = self.wait_for_pairing_code(session_id, timeout=timeout)
        return pairing_code_to_qr_image(code)


def _webhook_self_base_url() -> str:
    """
    Base URL do Django para webhooks Go → painel.
    Em produção não use host Docker Swarm (stack_servico): "_" quebra o Host header no Django.
    """
    import os

    from django.conf import settings as _s

    explicit = getattr(_s, 'NIOHUB_CALLS_WEBHOOK_SELF_URL', '').strip().rstrip('/')
    if explicit:
        host = (urlparse(explicit).hostname or '').lower()
        if host and '_' not in host:
            return explicit

    for candidate in (
        getattr(_s, 'BACKEND_URL', ''),
        getattr(_s, 'FRONTEND_URL', ''),
    ):
        base = (candidate or '').strip().rstrip('/')
        if not base:
            continue
        host = (urlparse(base).hostname or '').lower()
        if host and '_' not in host:
            return base

    subdomain = (os.environ.get('SUBDOMAIN') or '').strip()
    if subdomain:
        if subdomain.startswith('http://') or subdomain.startswith('https://'):
            return subdomain.rstrip('/')
        return f'https://{subdomain}'.rstrip('/')

    go_base = getattr(_s, 'NIOHUB_CALLS_BASE_URL', '').strip().lower()
    if '127.0.0.1' in go_base or 'localhost' in go_base or getattr(_s, 'DEBUG', False):
        return 'http://127.0.0.1:8011'

    return ''


def _call_webhook_url(canal) -> Optional[str]:
    """
    URL do Django para receber webhooks de chamada do Go.
    Inclui provedor_id na query para não depender de lookup pelo UUID da sessão.
    """
    provedor_id = getattr(getattr(canal, 'provedor', None), 'id', None) or getattr(canal, 'provedor_id', None)
    qs = f'?provedor_id={provedor_id}' if provedor_id else ''

    base = _webhook_self_base_url()
    if not base:
        return None
    return f'{base.rstrip("/")}/api/voice-calls/call-webhook/{qs}'


def _register_call_webhook(client: 'NioHubCallsClient', session_id: str, canal) -> None:
    url = _call_webhook_url(canal)
    if url:
        client.set_session_webhook(session_id, url)
        logger.info('[NioHubCalls] webhook registrado: %s → %s', session_id, url)


def setup_voice_calls(canal) -> Tuple[Dict[str, Any], Optional[str]]:
    client = get_voice_calls_client()
    name = session_name_for_canal(canal)
    existing = get_voice_calls_state(canal)
    session_id = existing.get('session_id')
    session: Dict[str, Any] = {}

    if session_id:
        session = client.get_session(str(session_id))

    if not session:
        found = client.find_session_by_name(name)
        if found:
            session = found
            session_id = found.get('id') or found.get('sessionId')

    if not session:
        created = client.create_session(name)
        session = created if isinstance(created, dict) else {}
        session_id = session.get('id') or session.get('sessionId')

    if not session_id:
        raise NioHubCallsError('Serviço de ligações não devolveu ID da sessão.')

    session_id = str(session_id)
    status = client.session_remote_status(session)
    qrcode = extract_qr_from_payload(session)

    if status != 'connected' and not qrcode:
        try:
            paired = client.pair_session(session_id)
            qrcode = extract_qr_from_payload(paired) or qrcode
        except NioHubCallsError:
            pass

    pairing_code = None
    if status != 'connected' and not qrcode:
        pairing_code = client.wait_for_pairing_code(session_id)
        qrcode = pairing_code_to_qr_image(pairing_code)

    if status != 'connected' and not qrcode:
        refreshed = client.get_session(session_id)
        status = client.session_remote_status(refreshed or session)

    state = {
        'session_id': session_id,
        'session_name': name,
        'status': status if status != 'unknown' else 'pairing',
        'enabled': True,
    }
    if pairing_code and state['status'] != 'connected':
        state['pairing_code'] = pairing_code
    if qrcode and state['status'] != 'connected':
        state['status'] = 'pairing'

    saved = save_voice_calls_state(canal, state)

    # Registrar webhook para que o Go nos notifique em tempo real sobre chamadas
    _register_call_webhook(client, session_id, canal)

    return saved, qrcode


def refresh_voice_calls_status(canal) -> Tuple[Dict[str, Any], Optional[str]]:
    state = get_voice_calls_state(canal)
    session_id = state.get('session_id')
    if not session_id:
        return state, None

    client = get_voice_calls_client()
    session = client.get_session(str(session_id))
    if not session:
        state['status'] = 'disconnected'
        save_voice_calls_state(canal, state)
        return state, None

    status = client.session_remote_status(session)
    remote_state = str(session.get('state') or '').lower()
    qrcode = None
    pairing_code = state.get('pairing_code')

    if status == 'connected':
        state.pop('pairing_code', None)
        state['status'] = 'connected'
    elif remote_state == 'qr':
        state['status'] = 'pairing'
        fresh_code = client.wait_for_pairing_code(str(session_id), timeout=3)
        if fresh_code:
            pairing_code = fresh_code
            state['pairing_code'] = fresh_code
        qrcode = pairing_code_to_qr_image(pairing_code)
    else:
        state['status'] = status
        if remote_state == 'logged_out':
            state.pop('pairing_code', None)

    state['enabled'] = True
    saved = save_voice_calls_state(canal, state)
    _register_call_webhook(client, str(session_id), canal)
    return saved, qrcode


def disable_voice_calls(canal) -> None:
    state = get_voice_calls_state(canal)
    session_id = state.get('session_id')
    if session_id and voice_calls_configured():
        try:
            get_voice_calls_client().delete_session(str(session_id))
        except NioHubCallsError as exc:
            logger.warning('[NioHubCalls] delete sessão %s: %s', session_id, exc)
    save_voice_calls_state(canal, None)


def normalize_voice_phone(raw: Any) -> str:
    from core.phone_utils import normalize_whatsapp_phone
    return normalize_whatsapp_phone(raw)

def linked_device_voice_phone(raw: Any) -> str:
    """
    PN/JID para whatsmeow (linked device).
    Cloud API usa 55+DDD+9+8 dígitos; chamadas usam 55+DDD+8 dígitos.
    """
    digits = normalize_voice_phone(raw)
    if len(digits) == 13 and digits.startswith('55') and digits[4] == '9':
        return digits[:4] + digits[5:]
    return digits


def resolve_voice_phone_for_contact(contact) -> str:
    """
    Número para discagem via linked device (whatsmeow).
    Preferir whatsapp_pn / whatsapp_wa_id — a normalização Cloud API pode
    inserir nono dígito e divergir do PN usado em chamadas (ex.: 556392484773 vs 5563992484773).
    """
    attrs = contact.additional_attributes if isinstance(getattr(contact, 'additional_attributes', None), dict) else {}
    for key in ('whatsapp_pn', 'whatsapp_wa_id', 'whatsapp_from'):
        raw = re.sub(r'\D', '', str(attrs.get(key) or ''))
        if raw:
            return linked_device_voice_phone(raw)
    return linked_device_voice_phone(getattr(contact, 'phone', ''))


def resolve_canal_with_voice_for_conversation(conversation):
    """Canal oficial com sessão de voz conectada para esta conversa."""
    from conversations.models import Conversation

    if not isinstance(conversation, Conversation):
        raise ValueError('Conversa inválida')
    inbox = conversation.inbox
    if not inbox:
        raise NioHubCallsError('Conversa sem caixa de entrada.', status_code=400)
    if inbox.channel_type not in ('whatsapp_oficial', 'whatsapp'):
        raise NioHubCallsError('Ligações disponíveis apenas em conversas WhatsApp.', status_code=400)

    canal = inbox.get_canal_instance()
    if not canal or canal.tipo != 'whatsapp_oficial':
        raise NioHubCallsError('Canal WhatsApp Oficial não encontrado para esta conversa.', status_code=400)

    state = get_voice_calls_state(canal)
    if state.get('status') != 'connected' or not state.get('session_id'):
        raise NioHubCallsError(
            'Ative as ligações em canal',
            status_code=400,
        )
    return canal, state


def _peer_phone_candidates(peer: str) -> list[str]:
    """Variações de dígitos para casar peer JID/LID com contatos."""
    if not peer:
        return []
    user_part = peer.split('@')[0]
    digits = re.sub(r'\D', '', user_part)
    if not digits:
        return []
    out = {digits, linked_device_voice_phone(digits)}
    norm = linked_device_voice_phone(digits)
    if len(norm) == 12 and norm.startswith('55'):
        out.add(norm[:4] + '9' + norm[4:])
    return [d for d in out if d]


def find_contact_for_voice_peer(peer: str, provedor) -> Optional[Any]:
    """Resolve contato a partir do peer da chamada (PN ou LID)."""
    from django.db.models import Q
    from conversations.models import Contact

    if not peer or not provedor:
        return None

    contacts = Contact.objects.filter(provedor=provedor)
    user_part = peer.split('@')[0]
    domain = peer.split('@')[1].lower() if '@' in peer else ''
    digits = re.sub(r'\D', '', user_part)
    lid = digits or user_part if (domain == 'lid' or peer.endswith('@lid')) else ''

    if domain == 'lid' or peer.endswith('@lid'):
        lid = digits or user_part
        lid_q = Q()
        for key in ('sender_lid', 'whatsapp_lid', 'lid'):
            lid_q |= Q(**{f'additional_attributes__{key}__icontains': lid})
        match = contacts.filter(lid_q).first()
        if match:
            return match

    candidates = set(_peer_phone_candidates(peer))
    if not candidates:
        return None

    for contact in contacts.iterator():
        phone_digits = re.sub(r'\D', '', getattr(contact, 'phone', '') or '')
        if phone_digits:
            variants = {phone_digits, linked_device_voice_phone(phone_digits)}
            if len(linked_device_voice_phone(phone_digits)) == 12:
                v = linked_device_voice_phone(phone_digits)
                variants.add(v[:4] + '9' + v[4:])
            if candidates & variants:
                return contact
        attrs = contact.additional_attributes if isinstance(contact.additional_attributes, dict) else {}
        for key in ('whatsapp_pn', 'whatsapp_wa_id', 'whatsapp_from', 'sender_lid'):
            raw = str(attrs.get(key) or '')
            raw_digits = re.sub(r'\D', '', raw)
            if not raw_digits:
                continue
            variants = {raw_digits, linked_device_voice_phone(raw_digits)}
            norm = linked_device_voice_phone(raw_digits)
            if len(norm) == 12 and norm.startswith('55'):
                variants.add(norm[:4] + '9' + norm[4:])
            if candidates & variants:
                return contact
            if domain == 'lid' and lid and lid in raw:
                return contact
    return None


def find_conversation_for_voice_peer(peer: str, provedor) -> Optional[Any]:
    """Conversa WhatsApp mais recente do contato identificado pelo peer."""
    from conversations.models import Conversation

    contact = find_contact_for_voice_peer(peer, provedor)
    if not contact:
        return None
    return (
        Conversation.objects.filter(
            contact=contact,
            inbox__channel_type__in=('whatsapp', 'whatsapp_oficial'),
        )
        .select_related('contact', 'inbox')
        .order_by('-updated_at')
        .first()
    )


def _is_generic_voice_contact_name(name: str) -> bool:
    if not name:
        return True
    n = str(name).strip()
    if not n or n == 'Cliente WhatsApp':
        return True
    return bool(re.match(r'^Cliente\s+\d{6,}$', n, re.I))


def _resolve_voice_display_name(contact, peer_name: str = '') -> Optional[str]:
    peer = str(peer_name or '').strip()
    crm = str(getattr(contact, 'name', '') or '').strip() if contact else ''
    # Preferir nome do CRM; notify do WhatsApp só como fallback.
    if crm and not _is_generic_voice_contact_name(crm):
        return crm
    if peer and not _is_generic_voice_contact_name(peer):
        return peer
    if crm:
        return crm
    return peer or None


def lookup_incoming_voice_call(
    peer: str, provedor, caller_pn: str = '', peer_name: str = ''
) -> Dict[str, Any]:
    """Metadados para o popup de chamada recebida."""
    contact = find_contact_for_voice_peer(peer, provedor)
    if not contact and caller_pn:
        contact = find_contact_for_voice_peer(caller_pn, provedor)
    conversation = None
    if contact:
        from conversations.models import Conversation

        conversation = (
            Conversation.objects.filter(
                contact=contact,
                inbox__channel_type__in=('whatsapp', 'whatsapp_oficial'),
            )
            .select_related('contact', 'inbox')
            .order_by('-updated_at')
            .first()
        )
    elif peer:
        conversation = find_conversation_for_voice_peer(peer, provedor)
    phone = ''
    if contact:
        phone = resolve_voice_phone_for_contact(contact) or re.sub(r'\D', '', getattr(contact, 'phone', '') or '')
    return {
        'peer': peer or '',
        'contact_id': contact.id if contact else None,
        'contact_name': _resolve_voice_display_name(contact, peer_name),
        'contact_phone': phone or None,
        'conversation_id': conversation.id if conversation else None,
        'provedor_id': getattr(provedor, 'id', None),
    }


def get_voice_call_capability(conversation) -> Dict[str, Any]:
    try:
        canal, state = resolve_canal_with_voice_for_conversation(conversation)
        phone = resolve_voice_phone_for_contact(conversation.contact)
        return {
            'available': bool(phone),
            'configured': voice_calls_configured(),
            'voice_status': state.get('status'),
            'session_id': state.get('session_id'),
            'canal_id': canal.id,
            'contact_phone': phone,
            'reason': None if phone else 'Contato sem telefone.',
            'hint': (
                'Ligações saem pelo número do QR, não pela Cloud API. '
                'Responda o contato pelo WhatsApp vinculado (dispositivo pareado) antes de ligar. '
                'Contatos só na API oficial tendem a falhar (erro 439). '
                'Áudio ao vivo exige build Go com -tags mlow.'
            ),
        }
    except NioHubCallsError as exc:
        return {
            'available': False,
            'configured': voice_calls_configured(),
            'voice_status': None,
            'reason': str(exc),
        }
    except Exception as exc:
        logger.warning('[NioHubCalls] capability: %s', exc)
        return {
            'available': False,
            'configured': voice_calls_configured(),
            'voice_status': None,
            'reason': 'Não foi possível verificar ligações.',
        }


def sync_all_voice_call_webhooks() -> int:
    """
    Re-registra webhooks no Go para todos os canais com ligações ativas.
    Executado no startup após deploy para corrigir URLs antigas (host Docker com '_').
    """
    if not voice_calls_configured():
        return 0
    try:
        client = get_voice_calls_client()
    except NioHubCallsNotConfigured:
        return 0

    from core.models import Canal

    updated = 0
    for canal in Canal.objects.filter(tipo='whatsapp_oficial', ativo=True).iterator():
        state = get_voice_calls_state(canal)
        session_id = str(state.get('session_id') or '').strip()
        if not session_id or not state.get('enabled'):
            continue
        url = _call_webhook_url(canal)
        if not url:
            continue
        try:
            client.set_session_webhook(session_id, url)
            updated += 1
            logger.info(
                '[NioHubCalls] webhook sincronizado canal=%s session=%s → %s',
                canal.id,
                session_id,
                url,
            )
        except NioHubCallsError as exc:
            logger.warning('[NioHubCalls] sync webhook canal=%s: %s', canal.id, exc)
    return updated
