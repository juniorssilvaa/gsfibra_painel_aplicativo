"""Métricas de uso (tokens / latência) por resposta da IA."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def log_usage(
    *,
    provedor_id: Optional[int],
    conversation_id: Optional[int],
    model: str,
    provider: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    latency_ms: Optional[float] = None,
    tool_summary: Optional[Dict[str, Any]] = None,
) -> None:
    logger.info(
        "[AI_USAGE] provedor=%s conv=%s provider=%s model=%s "
        "prompt_tokens=%s completion_tokens=%s total_tokens=%s latency_ms=%s tools=%s",
        provedor_id,
        conversation_id,
        provider,
        model,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        latency_ms,
        (tool_summary or {}).get("tools"),
    )
