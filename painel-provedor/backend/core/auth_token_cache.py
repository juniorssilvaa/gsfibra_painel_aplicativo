"""
Cache leve token -> user_id para evitar SELECT em Token a cada request HTTP/WS.
"""
from __future__ import annotations

import hashlib

from django.contrib.auth import get_user_model
from django.core.cache import cache

_TOKEN_USER_CACHE_TTL = 300  # 5 min — tokens mudam raramente


def _cache_key(token_key: str) -> str:
    digest = hashlib.sha256(token_key.encode("utf-8")).hexdigest()[:32]
    return f"auth_token_uid:{digest}"


def user_from_token_key(token_key: str):
    """Resolve usuário ativo a partir da chave do token DRF, com cache."""
    if not token_key:
        return None

    key = _cache_key(token_key)
    user_id = cache.get(key)
    User = get_user_model()

    if user_id is not None:
        try:
            return User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            cache.delete(key)
            return None

    from rest_framework.authtoken.models import Token

    try:
        token = Token.objects.select_related("user").get(key=token_key)
    except Token.DoesNotExist:
        return None

    if not token.user.is_active:
        return None

    cache.set(key, token.user_id, _TOKEN_USER_CACHE_TTL)
    return token.user


def invalidate_token_cache(token_key: str) -> None:
    if token_key:
        cache.delete(_cache_key(token_key))
