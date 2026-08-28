"""Configuração multi-provedor de IA (OpenAI / Gemini / DeepSeek)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models import Provedor

AI_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "base_url": None,
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1"],
        "key_hint": "sk-...",
        "docs_url": "https://platform.openai.com/api-keys",
    },
    "gemini": {
        "label": "Gemini (Google)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "default_model": "gemini-2.0-flash",
        "models": ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro"],
        "key_hint": "AIza... ou AQ....",
        "docs_url": "https://aistudio.google.com/apikey",
    },
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "key_hint": "sk-...",
        "docs_url": "https://platform.deepseek.com/api_keys",
    },
}

DEFAULT_OPENAI_MODEL = AI_PROVIDERS["openai"]["default_model"]
OPENAI_KEY_MISSING_MSG = (
    "Chave da API de IA não configurada. "
    "Configure em Integrações → Agente de IA no painel do provedor."
)


def get_provedor_ai_provider(provedor: "Provedor") -> str:
    if not provedor:
        return "openai"
    ext = provedor.integracoes_externas or {}
    provider = (ext.get("ai_provider") or "openai").strip().lower()
    return provider if provider in AI_PROVIDERS else "openai"


def get_provedor_openai_api_key(provedor: "Provedor") -> str:
    if not provedor:
        return ""
    ext = provedor.integracoes_externas or {}
    return (ext.get("openai_api_key") or ext.get("ai_api_key") or "").strip()


def get_provedor_ai_model(provedor: "Provedor") -> str:
    provider = get_provedor_ai_provider(provedor)
    defaults = AI_PROVIDERS[provider]
    if not provedor:
        return defaults["default_model"]
    ext = provedor.integracoes_externas or {}
    model = (ext.get("openai_model") or ext.get("ai_model") or "").strip()
    return model or defaults["default_model"]


def get_provedor_openai_model(provedor: "Provedor") -> str:
    return get_provedor_ai_model(provedor)
