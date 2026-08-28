"""
Cotação USD-BRL para Meta Analytics.

Ordem:
1. AWESOMEAPI_TOKEN no .env do painel → AwesomeAPI direto
2. Fallback: Superadmin GET /api/webhooks/provider/fx/usd-brl/ (chave + tarifas)
3. AwesomeAPI pública (dev)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from integrations.whatsapp_pricing_rates import (
    enrich_categories_with_rates,
    merge_rates,
    rates_table,
    total_from_categories,
)

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"ts": 0.0, "data": None, "rates": None}
_CACHE_TTL = 55


def _local_token() -> str:
    env = (os.environ.get("AWESOMEAPI_TOKEN") or "").strip()
    if env:
        return env
    try:
        from django.conf import settings as dj_settings

        return (getattr(dj_settings, "AWESOMEAPI_TOKEN", None) or "").strip()
    except Exception:
        return ""


def _fetch_awesome_direct(token: str) -> Optional[Dict[str, Any]]:
    url = "https://economia.awesomeapi.com.br/json/last/USD-BRL"
    headers = {"x-api-key": token} if token else {}
    params = {"token": token} if token else None
    resp = requests.get(url, headers=headers, params=params, timeout=12)
    resp.raise_for_status()
    payload = resp.json() if resp.content else {}
    row = payload.get("USDBRL") if isinstance(payload, dict) else None
    if not isinstance(row, dict):
        return None
    bid = float(row.get("bid") or 0)
    if bid <= 0:
        return None
    return {
        "pair": "USD-BRL",
        "code": row.get("code") or "USD",
        "codein": row.get("codein") or "BRL",
        "name": row.get("name") or "Dólar Americano/Real Brasileiro",
        "bid": bid,
        "ask": float(row.get("ask") or 0),
        "high": row.get("high"),
        "low": row.get("low"),
        "pct_change": row.get("pctChange"),
        "create_date": row.get("create_date"),
        "timestamp": row.get("timestamp"),
        "source": "awesomeapi_direct",
    }


def _fetch_via_superadmin() -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, float]]]:
    try:
        from integrations.superadmin_notifier import _resolve_provider_token, _superadmin_api_urls
    except Exception as exc:
        logger.info("[FX] superadmin_notifier indisponível: %s", exc)
        return None, None

    for base in _superadmin_api_urls():
        token = (_resolve_provider_token(base) or "").strip()
        if not token:
            continue
        url = f"{base.rstrip('/')}/api/webhooks/provider/fx/usd-brl/"
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=12,
            )
            if resp.status_code >= 400:
                logger.info("[FX] Superadmin FX HTTP %s em %s", resp.status_code, base)
                continue
            data = resp.json() if resp.content else {}
            quote = data.get("quote") if isinstance(data, dict) else None
            rates_raw = data.get("rates") if isinstance(data, dict) else None
            rates = merge_rates(rates_raw) if isinstance(rates_raw, dict) else None
            if isinstance(quote, dict) and float(quote.get("bid") or 0) > 0:
                quote = dict(quote)
                quote["source"] = "superadmin"
                return quote, rates
            if rates:
                return None, rates
        except Exception as exc:
            logger.info("[FX] Superadmin FX erro em %s: %s", base, exc)
    return None, None


def get_usd_brl_quote(*, force: bool = False) -> Optional[Dict[str, Any]]:
    now = time.time()
    if not force and _CACHE["data"] and (now - float(_CACHE["ts"])) < _CACHE_TTL:
        return _CACHE["data"]

    quote = None
    rates_from_sa = None
    local = _local_token()
    if local:
        try:
            quote = _fetch_awesome_direct(local)
        except Exception as exc:
            logger.warning("[FX] AwesomeAPI direta falhou: %s", exc)

    if not quote:
        try:
            quote = _fetch_awesome_direct("")
            if quote:
                quote["source"] = "awesomeapi_public"
        except Exception as exc:
            logger.info("[FX] AwesomeAPI pública falhou: %s", exc)

    try:
        sa_quote, sa_rates = _fetch_via_superadmin()
        if sa_rates:
            rates_from_sa = sa_rates
        if not quote and sa_quote:
            quote = sa_quote
    except Exception as exc:
        logger.info("[FX] Superadmin FX skip: %s", exc)

    if quote:
        _CACHE["ts"] = now
        _CACHE["data"] = quote
    if rates_from_sa:
        _CACHE["rates"] = rates_from_sa
    return quote or _CACHE["data"]


def get_pricing_rates() -> Dict[str, float]:
    if _CACHE.get("rates"):
        return dict(_CACHE["rates"])
    # Tenta Superadmin uma vez se ainda não cacheou
    _q, rates = _fetch_via_superadmin()
    if rates:
        _CACHE["rates"] = rates
        return rates
    return merge_rates()


def compute_spend_brl(
    *,
    messages_paid: int,
    meta_cost_usd: float,
    quote: Optional[Dict[str, Any]],
    categories: Optional[List[Dict[str, Any]]] = None,
    rates: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Gasto em BRL com tarifas por categoria:
    - volume_categoria × tarifa_USD × cotação USD-BRL
    - Se Meta retornou custo total > 0, usa esse total (ainda enriquece categorias)
    """
    rate_fx = float((quote or {}).get("bid") or 0)
    paid = max(0, int(messages_paid or 0))
    meta = float(meta_cost_usd or 0)
    rate_map = merge_rates(rates)

    enriched = enrich_categories_with_rates(categories or [], rate_map, rate_fx)
    cat_total_usd = total_from_categories(enriched)

    if rate_fx <= 0:
        return {
            "usd_rate": None,
            "cost_usd": round(meta or cat_total_usd, 6) if (meta or cat_total_usd) else None,
            "cost_brl": None,
            "mode": "no_fx",
            "label": "Cotação USD-BRL indisponível",
            "by_category": enriched,
            "rates_table": rates_table(rate_map),
        }

    if meta > 0:
        cost_usd = meta
        mode = "meta_x_fx"
        label = "Custo Meta (USD) × cotação AwesomeAPI"
    elif cat_total_usd > 0:
        cost_usd = cat_total_usd
        mode = "category_rates_x_fx"
        label = "Msgs por categoria × tarifa USD × cotação"
    elif paid > 0:
        # Fallback: todas as pagas como Utility
        utility = float(rate_map.get("UTILITY", 0.0068))
        cost_usd = paid * utility
        mode = "utility_fallback_x_fx"
        label = "Msgs pagas × tarifa Utility (fallback)"
        if not enriched:
            enriched = enrich_categories_with_rates(
                [{"key": "UTILITY", "label": "Utility", "volume": paid, "cost": 0}],
                rate_map,
                rate_fx,
            )
    else:
        cost_usd = 0.0
        mode = "zero"
        label = "Sem mensagens pagas no período"

    cost_brl = round(cost_usd * rate_fx, 2)

    return {
        "usd_rate": round(rate_fx, 4),
        "cost_usd": round(cost_usd, 6),
        "cost_brl": cost_brl,
        "mode": mode,
        "label": label,
        "messages_paid": paid,
        "by_category": enriched,
        "rates_table": rates_table(rate_map),
        "quote": {
            "bid": rate_fx,
            "ask": (quote or {}).get("ask"),
            "pct_change": (quote or {}).get("pct_change"),
            "create_date": (quote or {}).get("create_date"),
            "source": (quote or {}).get("source"),
        },
    }
