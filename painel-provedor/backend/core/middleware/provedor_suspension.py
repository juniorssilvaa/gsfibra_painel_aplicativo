"""
Bloqueia requests API de utilizadores cujo provedor está suspenso no superadmin.
"""
from __future__ import annotations

import re

from django.http import JsonResponse


_EXEMPT_PATHS = re.compile(
    r'^/api/(?:auth/|webhooks/|users/login|users/register|users/me/?$|provedores/status_pagamento/?$)',
    re.I,
)


def is_suspension_exempt_path(path: str) -> bool:
    """Rotas que a BlockedScreen precisa (login, perfil, fatura/PIX) mesmo com provedor suspenso."""
    return bool(_EXEMPT_PATHS.search(path or ''))


def _user_from_bearer_token(request):
    auth = (request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION') or '').strip()
    if not auth.lower().startswith('token '):
        return None
    key = auth[6:].strip()
    if not key:
        return None
    from core.auth_token_cache import user_from_token_key

    return user_from_token_key(key)


class ProvedorSuspensionMiddleware:
    """403 em rotas /api/ com token quando o tenant está suspenso no superadmin."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        if path.startswith('/api/') and not is_suspension_exempt_path(path):
            user = getattr(request, 'user', None)
            if not user or not getattr(user, 'is_authenticated', False):
                user = _user_from_bearer_token(request)
            if user and getattr(user, 'is_active', True):
                from core.login_provedor_access import api_access_denied_message_for_user

                denied = api_access_denied_message_for_user(user)
                if denied:
                    return JsonResponse(
                        {
                            'detail': denied,
                            'error': denied,
                            'code': 'PROVEDOR_PAYMENT_BLOCKED',
                        },
                        status=403,
                    )
        return self.get_response(request)
