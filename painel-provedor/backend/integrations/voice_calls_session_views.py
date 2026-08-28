"""
Proxy autenticado para ações de chamada por session_id (entrada + WebRTC).
"""
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.niohub_voice_calls import (
    NioHubCallsError,
    NioHubCallsNotConfigured,
    extract_sdp_from_request,
    get_voice_calls_client,
    validate_sdp_offer,
    voice_calls_configured,
)


def _err(exc):
    if isinstance(exc, NioHubCallsNotConfigured):
        return Response({'error': str(exc)}, status=503)
    if isinstance(exc, NioHubCallsError):
        code = exc.status_code if 400 <= exc.status_code < 600 else 502
        return Response({'error': str(exc)}, status=code)
    return Response({'error': str(exc)}, status=500)


class VoiceCallSessionWebRtcView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id, call_id):
        if not voice_calls_configured():
            return Response({'error': 'Serviço não configurado.'}, status=503)
        sdp_offer = extract_sdp_from_request(request)
        if not validate_sdp_offer(sdp_offer):
            return Response({'error': 'SDP WebRTC inválido ou ausente.'}, status=400)
        try:
            answer = get_voice_calls_client().send_webrtc_offer(str(session_id), str(call_id), sdp_offer)
            sdp_answer = answer.get('sdp_answer') or answer.get('sdp') or ''
            if not sdp_answer:
                return Response({'error': 'Resposta WebRTC inválida.'}, status=502)
            return Response({'sdp_answer': sdp_answer})
        except Exception as exc:
            return _err(exc)


class VoiceCallSessionAcceptView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id, call_id):
        try:
            get_voice_calls_client().accept_call(str(session_id), str(call_id))
            return Response({'success': True})
        except Exception as exc:
            return _err(exc)


class VoiceCallSessionRejectView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id, call_id):
        try:
            get_voice_calls_client().reject_call(str(session_id), str(call_id))
            return Response({'success': True})
        except Exception as exc:
            return _err(exc)


class VoiceCallSessionHangupView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id, call_id):
        try:
            get_voice_calls_client().end_call(str(session_id), str(call_id))
            return Response({'success': True})
        except Exception as exc:
            return _err(exc)
