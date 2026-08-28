"""
Actions REST para ligações de voz (NioHub Calls) no CanalViewSet.
Separado da API oficial Meta — importado em core.views.
"""
from typing import Optional

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from integrations.niohub_voice_calls import (
    NioHubCallsError,
    NioHubCallsNotConfigured,
    disable_voice_calls,
    get_voice_calls_state,
    refresh_voice_calls_status,
    setup_voice_calls,
    voice_calls_configured,
)


def _voice_calls_error_response(exc: Exception) -> Response:
    if isinstance(exc, NioHubCallsNotConfigured):
        return Response(
            {
                'error': str(exc),
                'code': 'voice_calls_not_configured',
                'configured': False,
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, NioHubCallsError):
        return Response(
            {'error': str(exc), 'code': 'voice_calls_service_error'},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _voice_calls_payload(canal, state, qrcode=None) -> dict:
    payload = {
        'voice_calls': state,
        'configured': voice_calls_configured(),
        'canal_id': canal.id,
    }
    if qrcode:
        payload['qrcode'] = qrcode
    return payload


def _ensure_official_canal(canal) -> Optional[Response]:
    if canal.tipo != 'whatsapp_oficial':
        return Response(
            {'error': 'Ligações por QR estão disponíveis apenas no canal WhatsApp Oficial.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not canal.ativo or (canal.status or '').lower() != 'connected':
        return Response(
            {'error': 'Conecte o WhatsApp Oficial antes de ativar ligações.'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


class CanalVoiceCallsMixin:
    @action(detail=True, methods=['post'], url_path='voice-calls/setup')
    def voice_calls_setup(self, request, pk=None):
        """Inicia sessão de voz (QR) ligada ao canal oficial — não altera a API Meta."""
        canal = self.get_object()
        blocked = _ensure_official_canal(canal)
        if blocked:
            return blocked
        try:
            state, qrcode = setup_voice_calls(canal)
            return Response(_voice_calls_payload(canal, state, qrcode))
        except Exception as exc:
            return _voice_calls_error_response(exc)

    @action(detail=True, methods=['get'], url_path='voice-calls/status')
    def voice_calls_status(self, request, pk=None):
        """Atualiza status da sessão de voz (pareamento ou conectado)."""
        canal = self.get_object()
        if canal.tipo != 'whatsapp_oficial':
            return Response({'error': 'Canal inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        state = get_voice_calls_state(canal)
        if not state.get('session_id'):
            return Response(
                _voice_calls_payload(canal, state or {'status': 'disabled', 'enabled': False})
            )
        if not voice_calls_configured():
            return Response(
                {
                    'voice_calls': state,
                    'configured': False,
                    'error': 'Serviço de ligações não configurado.',
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            state, qrcode = refresh_voice_calls_status(canal)
            return Response(_voice_calls_payload(canal, state, qrcode))
        except Exception as exc:
            return _voice_calls_error_response(exc)

    @action(detail=True, methods=['post'], url_path='voice-calls/repair')
    def voice_calls_repair(self, request, pk=None):
        """Gera novo QR para a sessão de voz existente."""
        canal = self.get_object()
        blocked = _ensure_official_canal(canal)
        if blocked:
            return blocked
        state = get_voice_calls_state(canal)
        if not state.get('session_id'):
            return Response(
                {'error': 'Nenhuma sessão de ligação ativa. Use setup primeiro.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            state, qrcode = setup_voice_calls(canal)
            return Response(_voice_calls_payload(canal, state, qrcode))
        except Exception as exc:
            return _voice_calls_error_response(exc)

    @action(detail=True, methods=['delete'], url_path='voice-calls')
    def voice_calls_disable(self, request, pk=None):
        """Remove sessão de voz; mensagens continuam só pela API oficial."""
        canal = self.get_object()
        if canal.tipo != 'whatsapp_oficial':
            return Response({'error': 'Canal inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            disable_voice_calls(canal)
            return Response({'success': True, 'voice_calls': {'status': 'disabled', 'enabled': False}})
        except Exception as exc:
            return _voice_calls_error_response(exc)
