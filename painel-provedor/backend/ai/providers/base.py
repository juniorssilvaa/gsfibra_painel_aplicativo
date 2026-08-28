"""Adapter base OpenAI-compatible para provedores de IA."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from openai import OpenAI

from ai.providers.config import (
    AI_PROVIDERS,
    get_provedor_ai_provider,
    get_provedor_ai_model,
    get_provedor_openai_api_key,
)


class BaseAIProvider:
    provider_name = "openai"

    def __init__(self, provedor):
        self.provedor = provedor
        self.api_key = get_provedor_openai_api_key(provedor)
        self.model = get_provedor_ai_model(provedor)

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def client(self) -> Optional[OpenAI]:
        if not self.api_key:
            return None
        cfg = AI_PROVIDERS.get(self.provider_name) or AI_PROVIDERS["openai"]
        kwargs: Dict[str, Any] = {"api_key": self.api_key}
        if cfg.get("base_url"):
            kwargs["base_url"] = cfg["base_url"]
        return OpenAI(**kwargs)

    def chat_completions_create(self, messages: List[Dict[str, Any]], **kwargs):
        client = self.client()
        if not client:
            raise RuntimeError("API key ausente")
        return client.chat.completions.create(
            model=kwargs.pop("model", self.model),
            messages=messages,
            **kwargs,
        )
