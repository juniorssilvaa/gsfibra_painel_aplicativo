"""
Webhook interno recebido do Go (NioHub Calls) para eventos de chamada.

Go → POST /api/voice-calls/call-webhook/
→ resolve provedor pelo session_name (niohub-p{provedor_id}-c{canal_id})
→ group_send para painel_{provedor_id} via Django Channels
→ PainelConsumer encaminha ao frontend via WebSocket
"""
import json
import logging
import re

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

_SESSION_NAME_RE = re.compile(r'niohub-p(\d+)-c(\d+)')


def _provedor_id_from_session(session_id: str) -> int | None:
    """Extrai provedor_id do session_id ou session_name (niohub-p{N}-c{M})."""
    if not session_id:
        return None
    m = _SESSION_NAME_RE.search(session_id)
    if m:
        return int(m.group(1))
    # Fallback: busca no banco
    try:
        from core.models import Canal
        from integrations.niohub_voice_calls import VOICE_CALLS_EXTRAS_KEY

        for canal in Canal.objects.filter(tipo='whatsapp_oficial').only('id', 'dados_extras', 'provedor_id'):
            extras = canal.dados_extras or {}
            vc = extras.get(VOICE_CALLS_EXTRAS_KEY) or {}
            if str(vc.get('session_id', '')) == str(session_id):
                pid = getattr(canal, 'provedor_id', None)
                if pid:
                    return int(pid)
    except Exception as exc:
        logger.debug('[VoiceCallWebhook] DB lookup failed: %s', exc)
    return None


def _push_to_painel(provedor_id: int, event_type: str, data: dict) -> None:
    channel_layer = get_channel_layer()
    if not channel_layer:
        logger.warning('[VoiceCallWebhook] channel_layer não disponível')
        return
    group = f'painel_{provedor_id}'
    message = {
        'type': 'voice_call_event',
        'voice_event': {
            'type': event_type,
            **data,
        },
    }
    try:
        async_to_sync(channel_layer.group_send)(group, message)
        logger.info('[VoiceCallWebhook] enviado para %s: %s callId=%s', group, event_type, data.get('id', ''))
    except Exception as exc:
        logger.warning('[VoiceCallWebhook] group_send falhou: %s', exc)


@method_decorator(csrf_exempt, name='dispatch')
class VoiceCallWebhookView(View):
    """Recebe webhooks do Go sem autenticação de token (chamado internamente)."""

    def post(self, request):
        try:
            body = json.loads(request.body or b'{}')
        except json.JSONDecodeError:
            return JsonResponse({'error': 'invalid json'}, status=400)

        session_id = str(body.get('session') or body.get('sessionId') or '')
        event = str(body.get('event') or '')
        data: dict = body.get('data') or {}

        logger.info('[VoiceCallWebhook] session=%s event=%s data=%s', session_id, event, data)

        provedor_id = None
        qp = request.GET.get('provedor_id')
        if qp and str(qp).isdigit():
            provedor_id = int(qp)
        if not provedor_id:
            provedor_id = _provedor_id_from_session(session_id)
        if not provedor_id:
            # Registrar mas não errar — sessão pode não ser do NioHub Hub
            logger.debug('[VoiceCallWebhook] provedor não encontrado para session=%s', session_id)
            return JsonResponse({'ok': True, 'warn': 'session not mapped'})

        # Normalizar tipo para o frontend
        type_map = {
            'call.incoming': 'incoming',
            'call.status': 'call-status',
            'call.ended': 'call-ended',
        }
        frontend_type = type_map.get(event, event)

        peer = str(data.get('peer') or '')
        caller_pn = str(data.get('callerPn') or data.get('caller_pn') or '')
        peer_name = str(data.get('peerName') or data.get('peer_name') or '')

        payload = {
            'sessionId': session_id,
            'id': data.get('callId', ''),
            'peer': peer,
            **data,
        }
        if caller_pn:
            payload['callerPn'] = caller_pn
            payload['caller_pn'] = caller_pn
        if peer_name:
            payload['peerName'] = peer_name
            payload['peer_name'] = peer_name
        if 'status' in data:
            payload['status'] = data['status']
        if 'reason' in data:
            payload['reason'] = data['reason']

        # Enriquecer incoming/ringing com nome do CRM assim que possível.
        if frontend_type in ('incoming', 'call-status') and (peer or caller_pn):
            try:
                from core.models import Provedor
                from integrations.niohub_voice_calls import lookup_incoming_voice_call

                provedor = Provedor.objects.filter(id=provedor_id).first()
                if provedor:
                    lookup = lookup_incoming_voice_call(
                        peer, provedor, caller_pn=caller_pn, peer_name=peer_name
                    )
                    if lookup.get('contact_name'):
                        payload['contact_name'] = lookup['contact_name']
                        payload['contactName'] = lookup['contact_name']
                    if lookup.get('contact_phone'):
                        payload['contact_phone'] = lookup['contact_phone']
                        payload['contactPhone'] = lookup['contact_phone']
                    if lookup.get('conversation_id'):
                        payload['conversation_id'] = lookup['conversation_id']
                        payload['conversationId'] = lookup['conversation_id']
            except Exception as exc:
                logger.debug('[VoiceCallWebhook] lookup enrich failed: %s', exc)

        _push_to_painel(provedor_id, frontend_type, payload)
        return JsonResponse({'ok': True})
