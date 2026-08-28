"""Rotação e invalidação de tokens DRF."""
from __future__ import annotations

from django.db import transaction
from rest_framework.authtoken.models import Token

from core.auth_token_cache import invalidate_token_cache


def rotate_user_token(user) -> Token:
    """Invalida token anterior (e cache) e emite um novo."""
    with transaction.atomic():
        old = Token.objects.filter(user=user).first()
        if old:
            old_key = old.key
            old.delete()
            invalidate_token_cache(old_key)
        return Token.objects.create(user=user)


def delete_user_token(user) -> None:
    """Remove token do usuário e invalida cache (logout)."""
    token = Token.objects.filter(user=user).first()
    if not token:
        return
    key = token.key
    token.delete()
    invalidate_token_cache(key)
