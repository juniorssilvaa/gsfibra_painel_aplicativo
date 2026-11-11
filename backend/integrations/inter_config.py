"""
Configuração do Banco Inter (OAuth + mTLS) a partir do SystemConfig.payload.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Optional, Tuple

from django.conf import settings

INTER_API_PRODUCTION = "https://cdpj.partners.bancointer.com.br"
INTER_API_SANDBOX = "https://cdpj-sandbox.partners.uatinter.co"

# Escopos mínimos para cobrança (boleto + Pix) e webhook
INTER_DEFAULT_SCOPE = (
    "boleto-cobranca.read boleto-cobranca.write "
    "cob.read cob.write webhook.read webhook.write"
)


def coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off", ""):
            return False
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return default
    return default


def _payload() -> dict:
    from super_core.models import SystemConfig

    config = SystemConfig.objects.first()
    if not config or not isinstance(config.payload, dict):
        return {}
    return config.payload


def is_inter_sandbox() -> bool:
    return coerce_bool(_payload().get("inter_sandbox"), default=True)


def get_inter_client_id() -> str:
    return str(_payload().get("inter_client_id") or "").strip()


def get_inter_client_secret() -> str:
    return str(_payload().get("inter_client_secret") or "").strip()


def get_inter_cert_pem() -> str:
    return str(_payload().get("inter_cert_pem") or "").strip()


def get_inter_key_pem() -> str:
    return str(_payload().get("inter_key_pem") or "").strip()


def get_inter_conta_corrente() -> str:
    return str(_payload().get("inter_conta_corrente") or "").strip()


def get_inter_webhook_auth_token() -> str:
    return str(_payload().get("inter_webhook_auth_token") or "").strip()


def get_inter_scope() -> str:
    return str(_payload().get("inter_scope") or INTER_DEFAULT_SCOPE).strip()


def get_inter_base_url() -> str:
    override = (getattr(settings, "INTER_BASE_URL", None) or "").strip()
    if override:
        return override.rstrip("/")
    return INTER_API_SANDBOX if is_inter_sandbox() else INTER_API_PRODUCTION


def is_inter_configured() -> bool:
    return bool(
        get_inter_client_id()
        and get_inter_client_secret()
        and get_inter_cert_pem()
        and get_inter_key_pem()
    )


def write_inter_cert_files() -> Tuple[Optional[str], Optional[str]]:
    """
    Grava .crt/.key temporários a partir do PEM no payload.
    Retorna (cert_path, key_path) ou (None, None).
    """
    cert = get_inter_cert_pem()
    key = get_inter_key_pem()
    if not cert or not key:
        return None, None

    base = Path(tempfile.gettempdir()) / "niohub_inter_certs"
    base.mkdir(parents=True, exist_ok=True)
    cert_path = base / "inter.crt"
    key_path = base / "inter.key"
    cert_path.write_text(cert if "BEGIN" in cert else cert, encoding="utf-8")
    key_path.write_text(key if "BEGIN" in key else key, encoding="utf-8")
    return str(cert_path), str(key_path)
