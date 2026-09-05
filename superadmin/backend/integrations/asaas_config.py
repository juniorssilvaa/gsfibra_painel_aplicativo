"""
Configuração centralizada do Asaas (sandbox vs produção) a partir do SystemConfig.
"""
from __future__ import annotations

from typing import Any, Optional

from django.conf import settings

ASAAS_API_PRODUCTION = "https://api.asaas.com/v3"
ASAAS_API_SANDBOX = "https://api-sandbox.asaas.com/v3"


def coerce_bool(value: Any, default: bool = True) -> bool:
    """Converte valores vindos do JSON do payload (bool, str, int) para bool."""
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


def is_asaas_sandbox() -> bool:
    """True = api-sandbox.asaas.com; False = api.asaas.com."""
    return coerce_bool(_payload().get("asaas_sandbox"), default=True)


def get_asaas_access_token() -> str:
    return str(_payload().get("asaas_access_token") or "").strip()


def get_asaas_webhook_auth_token() -> str:
    return str(_payload().get("asaas_webhook_auth_token") or "").strip()


def get_asaas_base_url() -> str:
    """
    URL base da API v3. Respeita ASAAS_BASE_URL no settings (override explícito),
    senão usa o checkbox asaas_sandbox do SystemConfig.
    """
    override = (getattr(settings, "ASAAS_BASE_URL", None) or "").strip()
    if override:
        return override.rstrip("/")
    return ASAAS_API_SANDBOX if is_asaas_sandbox() else ASAAS_API_PRODUCTION
