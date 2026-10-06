"""Relatório de entradas por anúncio Click-to-WhatsApp (tela Integrações → Meta)."""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from conversations.ad_referral import REPORT_DAYS, ad_referral_report
from conversations.ai_learning_views import _resolve_provedor_id


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ad_referrals_report(request):
    provedor_id = _resolve_provedor_id(request)
    if not provedor_id:
        return Response({'error': 'Provedor não encontrado'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        days = int(request.query_params.get('days') or 30)
    except (TypeError, ValueError):
        days = 30
    if days not in REPORT_DAYS:
        days = 30
    return Response(ad_referral_report(provedor_id, days))
