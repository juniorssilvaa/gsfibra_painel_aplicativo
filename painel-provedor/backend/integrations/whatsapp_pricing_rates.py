"""
Tarifas USD por categoria de mensagem WhatsApp (por mensagem entregue/paga).

Defaults = tarifas BR comuns (Utility / Marketing / Authentication).
Podem ser sobrescritas no Superadmin (SystemConfig) e injetadas via FX endpoint.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Tarifas padrão (USD por mensagem) — alinhadas à tabela do provedor
DEFAULT_RATES_USD: Dict[str, float] = {
    "UTILITY": 0.0068,
    "MARKETING": 0.0625,
    "AUTHENTICATION": 0.0068,
    "AUTHENTICATION_INTERNATIONAL": 0.0068,
    "MARKETING_LITE": 0.0625,
    "SERVICE": 0.0,
    "REFERRAL_CONVERSION": 0.0,
    "SESSION": 0.0,
    "TEMPLATES": 0.0068,  # fallback genérico → utility
}

CATEGORY_ORDER = ("UTILITY", "MARKETING", "AUTHENTICATION")

CATEGORY_LABELS = {
    "UTILITY": "Utility",
    "MARKETING": "Marketing",
    "AUTHENTICATION": "Authentication",
    "AUTHENTICATION_INTERNATIONAL": "Authentication (intl.)",
    "MARKETING_LITE": "Marketing Lite",
    "SERVICE": "Service (janela)",
    "SESSION": "Sessão (grátis)",
    "TEMPLATES": "Templates",
}


def normalize_category_key(key: str) -> str:
    k = (key or "").strip().upper()
    if k in ("UTILIDADE", "UTILITY"):
        return "UTILITY"
    if k in ("MARKETING",):
        return "MARKETING"
    if k in ("AUTHENTICATION", "AUTENTICACAO", "AUTENTICAÇÃO"):
        return "AUTHENTICATION"
    return k


def merge_rates(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    rates = dict(DEFAULT_RATES_USD)
    if not overrides:
        return rates
    mapping = {
        "utility": "UTILITY",
        "whatsapp_rate_utility_usd": "UTILITY",
        "marketing": "MARKETING",
        "whatsapp_rate_marketing_usd": "MARKETING",
        "authentication": "AUTHENTICATION",
        "whatsapp_rate_authentication_usd": "AUTHENTICATION",
    }
    for raw_key, value in overrides.items():
        cat = mapping.get(str(raw_key).lower()) or normalize_category_key(str(raw_key))
        try:
            rates[cat] = float(value)
        except (TypeError, ValueError):
            continue
    return rates


def rates_table(rates: Dict[str, float]) -> List[Dict[str, Any]]:
    rows = []
    for key in CATEGORY_ORDER:
        rows.append(
            {
                "key": key,
                "label": CATEGORY_LABELS.get(key, key.title()),
                "rate_usd": rates.get(key, 0.0),
                "currency": "USD",
                "vigencia": "período correspondente",
            }
        )
    return rows


def enrich_categories_with_rates(
    categories: List[Dict[str, Any]],
    rates: Dict[str, float],
    usd_brl: float,
) -> List[Dict[str, Any]]:
    enriched = []
    for cat in categories or []:
        key = normalize_category_key(cat.get("key") or "")
        volume = int(cat.get("volume") or 0)
        meta_cost = float(cat.get("cost") or 0)
        rate = float(rates.get(key, rates.get("TEMPLATES", 0.0)))
        # Prefer Meta cost se veio; senão volume × tarifa
        cost_usd = meta_cost if meta_cost > 0 else round(volume * rate, 6)
        cost_brl = round(cost_usd * usd_brl, 4) if usd_brl > 0 else None
        enriched.append(
            {
                **cat,
                "key": key or cat.get("key"),
                "label": cat.get("label") or CATEGORY_LABELS.get(key, key),
                "volume": volume,
                "rate_usd": rate,
                "cost_usd": round(cost_usd, 6),
                "cost_brl": cost_brl,
                "cost": round(cost_usd, 6),  # compat gráficos
            }
        )
    return enriched


def total_from_categories(categories: List[Dict[str, Any]]) -> float:
    return round(sum(float(c.get("cost_usd") or c.get("cost") or 0) for c in categories or []), 6)
