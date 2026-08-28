"""
Arquitetura de IA do NIO HUB.

Prompt Base + Tools + Registry + Executor + Providers.
"""

__all__ = [
    "ai_service",
    "openai_service",
    "AI_PROVIDERS",
    "get_provedor_ai_provider",
    "get_provedor_ai_model",
    "get_provedor_openai_api_key",
    "get_provedor_openai_model",
]


def __getattr__(name):
    if name in ("ai_service", "openai_service"):
        from ai.service import ai_service, openai_service

        return ai_service if name == "ai_service" else openai_service
    if name in (
        "AI_PROVIDERS",
        "get_provedor_ai_provider",
        "get_provedor_ai_model",
        "get_provedor_openai_api_key",
        "get_provedor_openai_model",
    ):
        from ai.providers import config as cfg

        return getattr(cfg, name)
    raise AttributeError(f"module 'ai' has no attribute {name!r}")
