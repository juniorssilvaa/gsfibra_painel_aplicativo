"""
Senha de primeiro acesso ao painel do provedor (Portainer / ensure_provider_admin).

Guardada em repouso encriptada com Fernet derivada do SECRET_KEY do superadmin.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_bootstrap(plain: str) -> str:
    if not plain:
        return ""
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_bootstrap(token: str) -> str:
    if not token or not str(token).strip():
        return ""
    raw = _fernet().decrypt(str(token).strip().encode("ascii"))
    return raw.decode("utf-8")


def decrypt_bootstrap_safe(token: str) -> str:
    try:
        return decrypt_bootstrap(token)
    except (InvalidToken, ValueError, TypeError):
        return ""
