"""
Canal de atendimento do aplicativo mobile.

O Superadmin encaminha mensagens do app (token sk_live_*) para
POST /api/webhooks/app-mobile/. Respostas do agente no painel
seguem para o Superadmin (push FCM + histórico no app).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional, Tuple

import requests
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from conversations.inbound_routing import reopen_conversation_for_bot
from conversations.models import Contact, Conversation, Inbox, Message, Team
from core.models import Canal, Provedor

logger = logging.getLogger(__name__)

CHANNEL_TYPE = 'app_mobile'
CONTACT_PHONE_PREFIX = 'app:'


def _digits(value) -> str:
    return re.sub(r'\D', '', str(value or ''))


def app_contact_phone(cpf: str) -> str:
    return f'{CONTACT_PHONE_PREFIX}{_digits(cpf)}'


def cpf_from_contact(contact: Contact) -> str:
    attrs = contact.additional_attributes or {}
    cpf = _digits(attrs.get('app_cpf') or attrs.get('cpf') or '')
    if cpf:
        return cpf
    phone = str(contact.phone or '')
    if phone.startswith(CONTACT_PHONE_PREFIX):
        return _digits(phone[len(CONTACT_PHONE_PREFIX):])
    return _digits(phone)


def get_or_create_app_mobile_channel(provedor: Provedor) -> Tuple[Canal, Inbox]:
    canal = Canal.objects.filter(provedor=provedor, tipo=CHANNEL_TYPE).first()
    if not canal:
        canal = Canal.objects.create(
            provedor=provedor,
            tipo=CHANNEL_TYPE,
            nome='Aplicativo',
            ativo=True,
            status='disconnected',
            ia_ativa=False,
        )
    inbox = Inbox.objects.filter(
        provedor=provedor,
        channel_type=CHANNEL_TYPE,
        channel_id=str(canal.id),
    ).first()
    if not inbox:
        inbox = Inbox.objects.filter(provedor=provedor, channel_type=CHANNEL_TYPE).first()
    if not inbox:
        inbox = Inbox.objects.create(
            provedor=provedor,
            channel_type=CHANNEL_TYPE,
            channel_id=str(canal.id),
            name=canal.nome or 'Aplicativo',
            is_active=True,
            additional_attributes={'canal_id': canal.id},
        )
    else:
        changed = []
        if inbox.channel_id != str(canal.id):
            inbox.channel_id = str(canal.id)
            changed.append('channel_id')
        if not inbox.is_active:
            inbox.is_active = True
            changed.append('is_active')
        if changed:
            inbox.save(update_fields=changed)
    return canal, inbox


def is_app_mobile_connected(canal: Optional[Canal]) -> bool:
    if not canal or not canal.ativo:
        return False
    token = (canal.token or '').strip()
    extras = canal.dados_extras or {}
    return token.startswith('sk_live_') and bool(extras.get('app_token_verified'))


def get_connected_app_mobile_channel(provedor: Provedor):
    canal = Canal.objects.filter(provedor=provedor, tipo=CHANNEL_TYPE).first()
    if not is_app_mobile_connected(canal):
        return None, None, (
            'Canal Aplicativo não conectado. Informe o token sk_live_ '
            'gerado no painel do app em Integrações.'
        )
    _, inbox = get_or_create_app_mobile_channel(provedor)
    return canal, inbox, None


def resolve_app_default_team(
    canal: Optional[Canal],
    provedor: Provedor,
    team_id_override=None,
) -> Optional[Team]:
    """Equipe configurada no painel do app ou em Integrações → Aplicativo."""
    raw = team_id_override
    if raw in (None, '', 0, '0'):
        raw = (canal.dados_extras or {}).get('app_default_team_id') if canal else None
    if raw in (None, '', 0, '0'):
        return None
    try:
        team_id = int(raw)
    except (TypeError, ValueError):
        return None
    return Team.objects.filter(id=team_id, provedor=provedor).first()


def apply_app_mobile_waiting_queue(
    conversation: Conversation,
    canal: Optional[Canal],
    provedor: Provedor,
    team_id_override=None,
) -> None:
    """App mobile sempre entra na fila humana (aba Espera), opcionalmente em uma equipe."""
    conversation.status = 'pending'
    conversation.assignee = None
    conversation.waiting_for_agent = True

    team = resolve_app_default_team(canal, provedor, team_id_override=team_id_override)
    attrs = dict(conversation.additional_attributes or {})
    if team:
        conversation.team = team
        attrs['assigned_team'] = {'id': team.id, 'name': team.name}
    else:
        conversation.team = None
        attrs.pop('assigned_team', None)
    conversation.additional_attributes = attrs
    conversation.save(
        update_fields=[
            'status',
            'team',
            'assignee',
            'waiting_for_agent',
            'additional_attributes',
            'updated_at',
        ]
    )


def normalize_app_default_team_extras(provedor: Provedor, extras: dict) -> dict:
    """Valida e enriquece app_default_team_id nos dados_extras do canal."""
    merged = dict(extras or {})
    raw = merged.get('app_default_team_id')
    if raw in (None, '', 0, '0'):
        merged.pop('app_default_team_id', None)
        merged.pop('app_default_team_name', None)
        return merged
    try:
        team_id = int(raw)
    except (TypeError, ValueError):
        raise ValueError('ID da equipe inválido.')
    team = Team.objects.filter(id=team_id, provedor=provedor).first()
    if not team:
        raise ValueError(f'Equipe #{team_id} não encontrada neste provedor.')
    merged['app_default_team_id'] = team.id
    merged['app_default_team_name'] = team.name
    return merged


def verify_sk_live_with_superadmin(app_token: str) -> Tuple[bool, str, dict]:
    """Confere no Superadmin se o sk_live_* pertence a este provedor."""
    app_token = (app_token or '').strip()
    if not app_token.startswith('sk_live_'):
        return False, 'Informe o token sk_live_ gerado no painel do app.', {}

    try:
        from integrations.superadmin_notifier import _resolve_provider_token, _superadmin_api_urls
    except Exception:
        return False, 'Não foi possível validar o token. Tente novamente.', {}

    last_error = 'Não foi possível validar o token. Tente novamente.'
    payload = {'token': app_token}
    for base in _superadmin_api_urls():
        token = _resolve_provider_token(base)
        if not token:
            last_error = 'Não foi possível validar o token. Tente novamente em instantes.'
            continue
        url = f'{base.rstrip("/")}/api/mobile-app/verify-app-token/'
        try:
            resp = requests.post(
                url,
                json=payload,
                headers={'Authorization': f'Bearer {token}'},
                timeout=15,
            )
        except requests.RequestException:
            last_error = 'Não foi possível validar o token. Tente novamente.'
            continue
        try:
            body = resp.json() if resp.content else {}
        except ValueError:
            body = {}
        if resp.ok and body.get('valid'):
            return True, '', body if isinstance(body, dict) else {}
        last_error = (
            (body.get('error') if isinstance(body, dict) else None)
            or 'Token inválido. Confira o sk_live_ no painel do app.'
        )
        if resp.status_code in (400, 401, 403):
            break
    return False, last_error, {}


def bind_app_mobile_token(canal: Canal, app_token: str) -> Canal:
    ok, error, body = verify_sk_live_with_superadmin(app_token)
    if not ok:
        from rest_framework.serializers import ValidationError
        raise ValidationError({'token': error})

    extras = dict(canal.dados_extras or {})
    extras['app_token_verified'] = True
    extras['app_token_suffix'] = body.get('token_suffix') or app_token[-8:]
    canal.token = app_token.strip()
    canal.status = 'connected'
    canal.ativo = True
    if not canal.nome:
        canal.nome = 'Aplicativo'
    canal.dados_extras = extras
    canal.save()
    get_or_create_app_mobile_channel(canal.provedor)
    return canal


def _strip_agent_signature(content: str) -> str:
    text = (content or '').strip()
    if not text:
        return ''
    text = re.sub(
        r'^\s*\*{1,2}.+?\s+disse:\*{0,2}\s*\n*',
        '',
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(r'^\s*\*[^*\n]+\*\s*\n+', '', text)
    return text.strip()


def _mirror_remote_media_locally(
    conversation_id: int,
    remote_url: str,
    file_name: str = '',
    mime_type: str = '',
) -> dict:
    """Baixa mídia do Superadmin para MEDIA local do painel (player sem CORS)."""
    if not remote_url or not str(remote_url).startswith(('http://', 'https://')):
        return {}
    try:
        from django.conf import settings

        resp = requests.get(remote_url, timeout=45)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning('[app-mobile] Falha ao espelhar mídia %s: %s', remote_url, exc)
        return {}

    media_dir = os.path.join(settings.MEDIA_ROOT, 'messages', str(conversation_id))
    os.makedirs(media_dir, exist_ok=True)

    base = (file_name or '').strip() or os.path.basename(str(remote_url).split('?', 1)[0]) or 'media.bin'
    base = re.sub(r'[^\w.\-]+', '_', base)[:120] or 'media.bin'
    if '.' not in base:
        mime = (mime_type or '').lower()
        if mime.startswith('audio/'):
            base = f'{base}.m4a'
        elif mime.startswith('image/'):
            base = f'{base}.jpg'
        elif mime.startswith('video/'):
            base = f'{base}.mp4'

    path = os.path.join(media_dir, base)
    if os.path.exists(path):
        stem, ext = os.path.splitext(base)
        base = f'{stem}_{int(__import__("time").time())}{ext}'
        path = os.path.join(media_dir, base)

    try:
        with open(path, 'wb') as fh:
            fh.write(resp.content)
    except OSError as exc:
        logger.warning('[app-mobile] Falha ao gravar mídia espelhada: %s', exc)
        return {}

    local_url = f'/api/media/messages/{conversation_id}/{base}/'
    return {
        'local_file_url': local_url,
        'file_path': path,
        'file_name': base,
        'file_size': len(resp.content),
    }


def _serialize_message(msg: Message) -> dict:
    attrs = msg.additional_attributes or {}
    # App precisa da URL pública do Superadmin (não do path local do painel).
    file_url = (
        attrs.get('app_file_url')
        or ''
    )
    if not file_url:
        candidate = attrs.get('file_url') or msg.file_url or ''
        if str(candidate).startswith(('http://', 'https://')):
            file_url = candidate
    content = msg.content or ''
    if not msg.is_from_customer:
        content = _strip_agent_signature(content)
    return {
        'id': msg.id,
        'content': content,
        'message_type': msg.message_type or 'text',
        'is_from_customer': bool(msg.is_from_customer),
        'created_at': msg.created_at.isoformat() if msg.created_at else None,
        'file_url': file_url or None,
        'file_name': msg.file_name or attrs.get('file_name') or None,
        'from_ai': bool(attrs.get('from_ai') or attrs.get('is_ai_response')),
        'agent_name': attrs.get('agent_name') or None,
    }


def ingest_inbound_message(
    provedor: Provedor,
    *,
    cpf: str,
    name: str = '',
    email: str = '',
    content: str = '',
    message_type: str = 'text',
    file_url: str = '',
    file_name: str = '',
    mime_type: str = '',
    app_default_team_id=None,
) -> Tuple[Optional[Conversation], Optional[Message], Optional[str]]:
    cpf = _digits(cpf)
    if not cpf:
        return None, None, 'cpf é obrigatório'

    canal, inbox, connect_err = get_connected_app_mobile_channel(provedor)
    if connect_err:
        return None, None, connect_err
    phone = app_contact_phone(cpf)
    display_name = (name or '').strip() or f'App {cpf}'

    contact, created = Contact.objects.get_or_create(
        phone=phone,
        provedor=provedor,
        defaults={
            'name': display_name,
            'email': email or None,
            'additional_attributes': {
                'source': CHANNEL_TYPE,
                'app_cpf': cpf,
            },
        },
    )
    attrs = dict(contact.additional_attributes or {})
    changed_contact = []
    if attrs.get('app_cpf') != cpf or attrs.get('source') != CHANNEL_TYPE:
        attrs['app_cpf'] = cpf
        attrs['source'] = CHANNEL_TYPE
        contact.additional_attributes = attrs
        changed_contact.append('additional_attributes')
    if email and not contact.email:
        contact.email = email
        changed_contact.append('email')
    if name and (created or contact.name == phone or contact.name.startswith('App ')):
        contact.name = display_name
        changed_contact.append('name')
    if changed_contact:
        contact.save(update_fields=list(dict.fromkeys(changed_contact)))

    # App mobile: fila humana (Espera). Sem equipe IA / chatbot.
    from conversations.inbound_routing import find_inbound_conversation
    conversation = find_inbound_conversation(
        contact, inbox, queryset=Conversation.objects.select_related('team', 'inbox', 'contact')
    )
    if not conversation:
        conversation = Conversation.objects.create(
            contact=contact,
            inbox=inbox,
            status='pending',
            team=None,
            assignee=None,
            waiting_for_agent=True,
        )
        apply_app_mobile_waiting_queue(conversation, canal, provedor, team_id_override=app_default_team_id)
    else:
        reopen_conversation_for_bot(
            conversation, ia_team=None, provedor=provedor, allow_closing_reopen=True
        )
        apply_app_mobile_waiting_queue(conversation, canal, provedor, team_id_override=app_default_team_id)

    allowed_types = {choice[0] for choice in Message.MESSAGE_TYPES}
    if message_type not in allowed_types:
        if (mime_type or '').startswith('image/'):
            message_type = 'image'
        elif (mime_type or '').startswith('audio/'):
            message_type = 'audio'
        elif (mime_type or '').startswith('video/'):
            message_type = 'video'
        elif file_url:
            message_type = 'document'
        else:
            message_type = 'text'

    additional = {
        'source': CHANNEL_TYPE,
        'app_cpf': cpf,
        'mime_type': mime_type or '',
        'app_file_url': file_url or '',
        'file_name': file_name or '',
    }
    stored_file_url = file_url or None
    if file_url:
        mirrored = _mirror_remote_media_locally(
            conversation.id,
            file_url,
            file_name=file_name or '',
            mime_type=mime_type or '',
        )
        if mirrored:
            additional.update(mirrored)
            stored_file_url = mirrored.get('local_file_url') or stored_file_url
            if mirrored.get('file_name'):
                file_name = mirrored['file_name']

    message = Message.objects.create(
        conversation=conversation,
        content=content or '',
        message_type=message_type,
        is_from_customer=True,
        file_url=stored_file_url,
        file_name=file_name or None,
        additional_attributes=additional,
    )

    # Canal Aplicativo: só atendimento humano no painel — sem IA/chatbot.
    return conversation, message, None


def send_app_mobile_outbound(
    conversation: Conversation,
    content: str,
    message_type: str = 'text',
    *,
    file_path: str = None,
    file_name: str = None,
    mime_type: str = None,
    file_url: str = None,
) -> Tuple[bool, object]:
    contact = conversation.contact
    if not contact:
        return False, 'Contato ausente'
    cpf = cpf_from_contact(contact)
    if not cpf:
        return False, 'CPF do cliente não encontrado no contato do app'

    try:
        from integrations.superadmin_notifier import _resolve_provider_token, _superadmin_api_url
    except Exception as exc:
        return False, f'Superadmin notifier indisponível: {exc}'

    superadmin_url = _superadmin_api_url()
    token = _resolve_provider_token(superadmin_url)
    if not token:
        return False, 'Token de integração com o Superadmin não configurado'

    url = f'{superadmin_url.rstrip("/")}/v1/support/outbound/'
    headers = {'Authorization': f'Bearer {token}'}
    data = {
        'cpf': cpf,
        'content': content or '',
        'message_type': message_type or 'text',
        'file_name': file_name or '',
        'mime_type': mime_type or '',
    }
    agent = getattr(conversation, 'assignee', None)
    if agent is not None:
        agent_name = (agent.get_full_name() or '').strip() or (getattr(agent, 'username', None) or '').strip()
        if agent_name:
            data['agent_name'] = agent_name
    if file_url:
        data['file_url'] = file_url

    fh = None
    files = None
    try:
        if file_path and os.path.isfile(file_path):
            fh = open(file_path, 'rb')
            files = {
                'file': (
                    file_name or os.path.basename(file_path),
                    fh,
                    mime_type or 'application/octet-stream',
                )
            }
        resp = requests.post(url, data=data, files=files, headers=headers, timeout=30)
    except requests.RequestException as exc:
        logger.warning('[app-mobile] outbound falhou: %s', exc)
        return False, str(exc)
    finally:
        if fh:
            try:
                fh.close()
            except Exception:
                pass

    try:
        body = resp.json()
    except ValueError:
        body = {'raw': (resp.text or '')[:400]}

    if not resp.ok:
        err = body.get('error') if isinstance(body, dict) else None
        return False, err or f'HTTP {resp.status_code}'
    return True, body


def _authorize_superadmin(request):
    from core.views import _is_superadmin_integration_authorized

    ok, _mode = _is_superadmin_integration_authorized(request)
    return ok


def _resolve_provedor_from_request(request, payload: dict):
    pid = payload.get('provedor_id') or request.GET.get('provedor_id')
    if pid not in (None, ''):
        try:
            provedor = Provedor.objects.filter(id=int(pid)).first()
            if provedor:
                return provedor, None
        except (TypeError, ValueError):
            pass
    qs = Provedor.objects.all()
    if qs.count() == 1:
        return qs.first(), None
    return None, 'Provedor não encontrado neste painel'


class AppMobileInboundWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        if not _authorize_superadmin(request):
            return Response({'error': 'Unauthorized'}, status=401)
        payload = dict(request.data) if isinstance(request.data, dict) else {}
        provedor, err = _resolve_provedor_from_request(request, payload)
        if err:
            return Response({'error': err}, status=400)

        conversation, message, ingest_err = ingest_inbound_message(
            provedor,
            cpf=payload.get('cpf') or '',
            name=payload.get('name') or '',
            email=payload.get('email') or '',
            content=payload.get('content') or payload.get('message') or '',
            message_type=payload.get('message_type') or 'text',
            file_url=payload.get('file_url') or '',
            file_name=payload.get('file_name') or '',
            mime_type=payload.get('mime_type') or '',
            app_default_team_id=payload.get('app_default_team_id'),
        )
        if ingest_err:
            return Response({'error': ingest_err}, status=400)
        return Response({
            'success': True,
            'conversation_id': conversation.id if conversation else None,
            'message': _serialize_message(message) if message else None,
        }, status=201)


class AppMobileMessagesWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        if not _authorize_superadmin(request):
            return Response({'error': 'Unauthorized'}, status=401)
        payload = {'provedor_id': request.GET.get('provedor_id')}
        provedor, err = _resolve_provedor_from_request(request, payload)
        if err:
            return Response({'error': err}, status=400)

        cpf = _digits(request.GET.get('cpf'))
        if not cpf:
            return Response({'error': 'cpf é obrigatório'}, status=400)

        canal, inbox, connect_err = get_connected_app_mobile_channel(provedor)
        if connect_err:
            return Response({'error': connect_err, 'messages': []}, status=400)
        phone = app_contact_phone(cpf)
        contact = Contact.objects.filter(phone=phone, provedor=provedor).first()
        if not contact:
            return Response({
                'success': True,
                'conversation_id': None,
                'channel': CHANNEL_TYPE,
                'messages': [],
            })

        conversation = Conversation.objects.filter(contact=contact, inbox=inbox).order_by('-id').first()
        if not conversation:
            return Response({
                'success': True,
                'conversation_id': None,
                'channel': CHANNEL_TYPE,
                'messages': [],
            })

        qs = Message.objects.filter(conversation=conversation).order_by('created_at')
        after_id = request.GET.get('after_id')
        if after_id and str(after_id).isdigit():
            qs = qs.filter(id__gt=int(after_id))

        messages = [_serialize_message(m) for m in qs[:200]]
        return Response({
            'success': True,
            'conversation_id': conversation.id,
            'channel': CHANNEL_TYPE,
            'messages': messages,
        })
