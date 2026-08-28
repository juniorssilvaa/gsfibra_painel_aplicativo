"""
Ligações de voz por conversa — proxy autenticado para NioHub Calls.
Não altera API oficial Meta.
"""
from typing import Optional

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from integrations.niohub_voice_calls import (
    NioHubCallsError,
    NioHubCallsNotConfigured,
    extract_sdp_from_request,
    get_voice_call_capability,
    get_voice_calls_client,
    linked_device_voice_phone,
    resolve_voice_phone_for_contact,
    resolve_canal_with_voice_for_conversation,
    validate_sdp_offer,
    voice_calls_configured,
)

# IDs de chamada WhatsApp são hex (ex.: 00A7B355…). Evita colidir com rotas literais
# como voice-call/start/ ou voice-call/capability/ no padrão voice-call/{call_id}/.
VOICE_CALL_ID_URL = r'(?P<call_id>[0-9A-Fa-f-]{8,64})'


def _voice_error(exc: Exception) -> Response:
    if isinstance(exc, NioHubCallsNotConfigured):
        return Response({'error': str(exc), 'code': 'voice_calls_not_configured'}, status=503)
    if isinstance(exc, NioHubCallsError):
        code = exc.status_code if 400 <= exc.status_code < 600 else 502
        if code >= 500 and 'sem sessão e2e' in str(exc).lower():
            code = 400
        msg = str(exc)
        prefix = 'Serviço de ligações: '
        if msg.startswith(prefix):
            msg = msg[len(prefix):]
        return Response({'error': msg}, status=code)
    return Response({'error': str(exc)}, status=500)


class ConversationVoiceCallsMixin:
    @action(detail=True, methods=['get'], url_path='voice-call/capability')
    def voice_call_capability(self, request, pk=None):
        conversation = self.get_object()
        return Response(get_voice_call_capability(conversation))

    @action(detail=True, methods=['post'], url_path='voice-call/start')
    def voice_call_start(self, request, pk=None):
        conversation = self.get_object()
        if not voice_calls_configured():
            return Response({'error': 'Serviço de ligações não configurado.'}, status=503)
        try:
            _, state = resolve_canal_with_voice_for_conversation(conversation)
            phone = linked_device_voice_phone(
                request.data.get('phone') or resolve_voice_phone_for_contact(conversation.contact)
            )
            if not phone:
                return Response({'error': 'Telefone do contato inválido.'}, status=400)
            session_id = str(state['session_id'])
            client = get_voice_calls_client()
            result = client.start_call(session_id, phone)
            call_id = None
            if isinstance(result, dict):
                call_obj = result.get('call') or result
                call_id = call_obj.get('callId') or call_obj.get('id')
            if not call_id:
                return Response({'error': 'Serviço não devolveu ID da chamada.'}, status=502)
            return Response({
                'call_id': str(call_id),
                'session_id': session_id,
                'phone': phone,
            })
        except Exception as exc:
            return _voice_error(exc)

    @action(detail=True, methods=['post'], url_path=rf'voice-call/{VOICE_CALL_ID_URL}/webrtc')
    def voice_call_webrtc(self, request, pk=None, call_id=None):
        conversation = self.get_object()
        sdp_offer = extract_sdp_from_request(request)
        if not validate_sdp_offer(sdp_offer):
            return Response({'error': 'SDP WebRTC inválido ou ausente.'}, status=400)
        try:
            _, state = resolve_canal_with_voice_for_conversation(conversation)
            session_id = str(state['session_id'])
            client = get_voice_calls_client()
            answer = client.send_webrtc_offer(session_id, str(call_id), sdp_offer)
            sdp_answer = answer.get('sdp_answer') or answer.get('sdp') or ''
            if not sdp_answer:
                return Response({'error': 'Resposta WebRTC inválida do serviço.'}, status=502)
            return Response({'sdp_answer': sdp_answer})
        except Exception as exc:
            return _voice_error(exc)

    @action(detail=True, methods=['post'], url_path=rf'voice-call/{VOICE_CALL_ID_URL}/accept')
    def voice_call_accept(self, request, pk=None, call_id=None):
        conversation = self.get_object()
        try:
            _, state = resolve_canal_with_voice_for_conversation(conversation)
            get_voice_calls_client().accept_call(str(state['session_id']), str(call_id))
            return Response({'success': True})
        except Exception as exc:
            return _voice_error(exc)

    @action(detail=True, methods=['post'], url_path=rf'voice-call/{VOICE_CALL_ID_URL}/reject')
    def voice_call_reject(self, request, pk=None, call_id=None):
        conversation = self.get_object()
        try:
            _, state = resolve_canal_with_voice_for_conversation(conversation)
            get_voice_calls_client().reject_call(str(state['session_id']), str(call_id))
            return Response({'success': True})
        except Exception as exc:
            return _voice_error(exc)

    @action(detail=True, methods=['delete'], url_path=rf'voice-call/{VOICE_CALL_ID_URL}')
    def voice_call_hangup(self, request, pk=None, call_id=None):
        conversation = self.get_object()
        try:
            _, state = resolve_canal_with_voice_for_conversation(conversation)
            get_voice_calls_client().end_call(str(state['session_id']), str(call_id))
            return Response({'success': True})
        except Exception as exc:
            return _voice_error(exc)
