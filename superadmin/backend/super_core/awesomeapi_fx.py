"""
Cotação USD-BRL via AwesomeAPI (chave em SystemConfig.payload.awesomeapi_token).
Docs: https://economia.awesomeapi.com.br/json/last/USD-BRL
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

from .models import SystemConfig

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"ts": 0.0, "data": None}
_CACHE_TTL = 55  # segundos (API cacheia 60s sem token)


def get_awesomeapi_token() -> str:
    config = SystemConfig.objects.first()
    if not config or not isinstance(config.payload, dict):
        return ""
    return (
        (config.payload.get("awesomeapi_token") or config.payload.get("AWESOMEAPI_TOKEN") or "")
        .strip()
    )


def fetch_usd_brl(*, force: bool = False) -> Optional[Dict[str, Any]]:
    """
    Retorna dict com bid/ask/pctChange/create_date ou None.
    """
    now = time.time()
    if not force and _CACHE["data"] and (now - float(_CACHE["ts"])) < _CACHE_TTL:
        return _CACHE["data"]

    token = get_awesomeapi_token()
    url = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
    headers = {}
    params = {}
    if token:
        headers["x-api-key"] = token
        params["token"] = token

    try:
        resp = requests.get(url, headers=headers, params=params or None, timeout=12)
        resp.raise_for_status()
        payload = resp.json() if resp.content else {}
    except Exception as exc:
        logger.warning("[AwesomeAPI] falha ao buscar USD-BRL: %s", exc)
        return _CACHE["data"]  # stale se houver

    row = payload.get("USDBRL") if isinstance(payload, dict) else None
    if not isinstance(row, dict):
        logger.warning("[AwesomeAPI] resposta sem USDBRL: %s", str(payload)[:200])
        return _CACHE["data"]

    try:
        bid = float(row.get("bid") or 0)
        ask = float(row.get("ask") or 0)
    except (TypeError, ValueError):
        return _CACHE["data"]

    if bid <= 0:
        return _CACHE["data"]

    data = {
        "pair": "USD-BRL",
        "code": row.get("code") or "USD",
        "codein": row.get("codein") or "BRL",
        "name": row.get("name") or "Dólar Americano/Real Brasileiro",
        "bid": bid,
        "ask": ask,
        "high": row.get("high"),
        "low": row.get("low"),
        "pct_change": row.get("pctChange"),
        "create_date": row.get("create_date"),
        "timestamp": row.get("timestamp"),
    }
    _CACHE["ts"] = now
    _CACHE["data"] = data
    return data


def get_whatsapp_message_rates() -> Dict[str, float]:
    """Tarifas USD/msg configuráveis no SystemConfig (com defaults)."""
    defaults = {
        "UTILITY": 0.0068,
        "MARKETING": 0.0625,
        "AUTHENTICATION": 0.0068,
    }
    config = SystemConfig.objects.first()
    payload = config.payload if config and isinstance(config.payload, dict) else {}
    try:
        defaults["UTILITY"] = float(
            payload.get("whatsapp_rate_utility_usd", defaults["UTILITY"])
        )
        defaults["MARKETING"] = float(
            payload.get("whatsapp_rate_marketing_usd", defaults["MARKETING"])
        )
        defaults["AUTHENTICATION"] = float(
            payload.get("whatsapp_rate_authentication_usd", defaults["AUTHENTICATION"])
        )
    except (TypeError, ValueError):
        pass
    return defaults
