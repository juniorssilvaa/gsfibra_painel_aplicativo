"""Política de Privacidade e Termos de Uso do app dos atendentes (textos definidos no superadmin)."""
import logging

import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)

_CACHE_KEY = 'operator_app_legal_texts'
_FALLBACK_KEY = 'operator_app_legal_texts_last_ok'
_CACHE_SECONDS = 120


def _superadmin_base_url():
    for name in ('SUPERADMIN_API_URL', 'SUPERADMIN_RESOLVE_API_URL', 'SUPERADMIN_ID_PROVEDOR_API'):
        url = str(getattr(settings, name, '') or '').strip().rstrip('/')
        if url:
            return url
    return ''


@api_view(['GET'])
@authentication_classes([])
@permission_classes([AllowAny])
def operator_app_legal(request):
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return Response(cached)

    base = _superadmin_base_url()
    data = None
    if base:
        try:
            resp = requests.get(f'{base}/api/public/operator-app/legal/', timeout=8)
            if resp.ok:
                body = resp.json()
                data = {
                    'privacy_policy': str(body.get('privacy_policy') or ''),
                    'terms_of_use': str(body.get('terms_of_use') or ''),
                    'updated_at': body.get('updated_at'),
                }
            else:
                logger.warning('[app-legal] superadmin HTTP %s', resp.status_code)
        except Exception as exc:
            logger.warning('[app-legal] falha ao consultar superadmin: %s', exc)

    if data is None:
        data = cache.get(_FALLBACK_KEY) or {'privacy_policy': '', 'terms_of_use': '', 'updated_at': None}
        cache.set(_CACHE_KEY, data, 60)
        return Response(data)

    cache.set(_CACHE_KEY, data, _CACHE_SECONDS)
    cache.set(_FALLBACK_KEY, data, None)
    return Response(data)
