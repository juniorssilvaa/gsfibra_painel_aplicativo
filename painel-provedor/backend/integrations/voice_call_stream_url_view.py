"""
URL do stream SSE (Go direto quando o browser alcança o serviço).
Não embute mais o token DRF na query do proxy.
"""
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.niohub_voice_calls import build_voice_calls_sse_url, voice_calls_configured


class VoiceCallStreamUrlView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not voice_calls_configured():
            return Response({
                'use_proxy': True,
                'events_url': None,
                'proxy_path': '/api/voice-calls/events/',
            })

        direct = build_voice_calls_sse_url(f'user-{request.user.id}')
        if direct:
            return Response({'use_proxy': False, 'events_url': direct})

        return Response({
            'use_proxy': True,
            'events_url': None,
            'proxy_path': '/api/voice-calls/events/',
        })
