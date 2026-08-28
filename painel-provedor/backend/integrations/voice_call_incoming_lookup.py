"""
Lookup de contato/conversa para chamadas recebidas (peer JID/LID → CRM).
"""
from rest_framework.authentication import TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Provedor
from integrations.niohub_voice_calls import lookup_incoming_voice_call, voice_calls_configured


def _user_provedor(user, provedor_id_param=None):
    if user.user_type == 'superadmin' and provedor_id_param:
        try:
            pid = int(provedor_id_param)
        except (TypeError, ValueError):
            return None
        return Provedor.objects.filter(id=pid).first()
    if hasattr(user, 'provedor') and user.provedor:
        return user.provedor
    return user.provedores_admin.first()


class VoiceCallIncomingLookupView(APIView):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not voice_calls_configured():
            return Response({'error': 'Serviço não configurado.'}, status=503)

        peer = (request.query_params.get('peer') or '').strip()
        if not peer:
            return Response({'error': 'Parâmetro peer é obrigatório.'}, status=400)

        provedor = _user_provedor(request.user, request.query_params.get('provedor_id'))
        if not provedor:
            return Response({'error': 'Provedor não encontrado.'}, status=403)

        caller_pn = (request.query_params.get('caller_pn') or '').strip()
        peer_name = (request.query_params.get('peer_name') or '').strip()
        return Response(lookup_incoming_voice_call(peer, provedor, caller_pn=caller_pn, peer_name=peer_name))
