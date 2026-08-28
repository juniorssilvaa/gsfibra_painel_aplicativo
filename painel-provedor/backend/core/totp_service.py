"""
Autenticação TOTP (2FA) para utilizadores do painel Niohub.
"""
import base64
import io
import logging
from typing import Optional

import pyotp
import qrcode
from django.conf import settings

logger = logging.getLogger(__name__)

ISSUER_NAME = 'NioHub'


def generate_secret() -> str:
    return pyotp.random_base32()


def mask_secret(secret: str) -> str:
    raw = (secret or '').strip()
    if len(raw) <= 4:
        return '****'
    return f"{'*' * max(len(raw) - 4, 8)}{raw[-4:]}"


def provisioning_uri(*, secret: str, username: str, email: str = '') -> str:
    label = email or username or 'user'
    return pyotp.TOTP(secret).provisioning_uri(name=label, issuer_name=ISSUER_NAME)


def verify_code(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    normalized = ''.join(ch for ch in str(code).strip() if ch.isdigit())
    if len(normalized) != 6:
        return False
    try:
        totp = pyotp.TOTP(secret)
        return totp.verify(normalized, valid_window=1)
    except Exception as exc:
        logger.warning('[2FA] Falha ao validar OTP: %s', exc)
        return False


def qr_code_data_url(uri: str) -> Optional[str]:
    if not uri:
        return None
    try:
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        b64 = base64.b64encode(buffer.getvalue()).decode('ascii')
        return f'data:image/png;base64,{b64}'
    except Exception as exc:
        logger.error('[2FA] Erro ao gerar QR code: %s', exc)
        return None


def ensure_user_totp_secret(user) -> str:
    """Garante secret TOTP no utilizador (ainda não ativa 2FA até confirmar OTP)."""
    if user.totp_secret:
        return user.totp_secret
    secret = generate_secret()
    user.totp_secret = secret
    user.save(update_fields=['totp_secret', 'updated_at'])
    return secret


def build_setup_payload(user) -> dict:
    secret = ensure_user_totp_secret(user)
    uri = provisioning_uri(
        secret=secret,
        username=user.username,
        email=user.email or '',
    )
    return {
        'is_active': bool(user.totp_enabled),
        'secret_masked': mask_secret(secret),
        'qr_code': qr_code_data_url(uri),
        'created_at': user.totp_enabled_at.isoformat() if user.totp_enabled_at else None,
        'updated_at': user.updated_at.isoformat() if user.updated_at else None,
        'username': user.username,
    }
