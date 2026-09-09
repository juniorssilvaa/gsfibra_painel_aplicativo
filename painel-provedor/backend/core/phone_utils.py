"""Normalização de telefone para WhatsApp (E.164 sem '+')."""
from __future__ import annotations

import re


def digits_only(value: str | None) -> str:
    return re.sub(r"\D", "", str(value or ""))


def looks_like_brazilian_local(digits: str) -> bool:
    """Número BR sem DDI: DDD+fixo (10) ou DDD+9+móvel (11)."""
    d = digits_only(digits)
    if len(d) == 10:
        return bool(re.fullmatch(r"[1-9][1-9]\d{8}", d))
    if len(d) == 11:
        return bool(re.fullmatch(r"[1-9][1-9]9\d{8}", d))
    return False


def normalize_whatsapp_phone(value: str | None) -> str:
    """
    Mantém DDI internacional (+1, +351, +55, etc.).
    Só prefixa 55 quando o número parece telefone BR local (10/11 dígitos)
    e NÃO veio com '+' explícito de outro país.
    """
    raw = str(value or "").strip()
    d = digits_only(raw)
    if not d:
        return ""

    # Já veio com DDI explícito (ex.: +1..., +351..., +55...)
    if raw.startswith("+"):
        return d

    if not d.startswith("55") and looks_like_brazilian_local(d):
        d = f"55{d}"
    return d


def normalize_whatsapp_phone_e164(value: str | None) -> str:
    """Mesmo que normalize_whatsapp_phone, com prefixo '+' (Meta Cloud API)."""
    d = normalize_whatsapp_phone(value)
    return f"+{d}" if d else ""


def is_valid_whatsapp_phone(value: str | None) -> bool:
    d = normalize_whatsapp_phone(value)
    return bool(re.fullmatch(r"[1-9]\d{7,14}", d))
