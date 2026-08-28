from ai.providers.config import (
    AI_PROVIDERS,
    get_provedor_ai_provider,
    get_provedor_ai_model,
    get_provedor_openai_api_key,
    get_provedor_openai_model,
    OPENAI_KEY_MISSING_MSG,
)
from ai.providers.openai import OpenAIProvider
from ai.providers.gemini import GeminiProvider
from ai.providers.deepseek import DeepSeekProvider


def get_provider_client(provedor):
    """Retorna o adapter do provedor de IA configurado."""
    name = get_provedor_ai_provider(provedor)
    if name == "gemini":
        return GeminiProvider(provedor)
    if name == "deepseek":
        return DeepSeekProvider(provedor)
    return OpenAIProvider(provedor)


__all__ = [
    "AI_PROVIDERS",
    "get_provedor_ai_provider",
    "get_provedor_ai_model",
    "get_provedor_openai_api_key",
    "get_provedor_openai_model",
    "OPENAI_KEY_MISSING_MSG",
    "get_provider_client",
    "OpenAIProvider",
    "GeminiProvider",
    "DeepSeekProvider",
]
