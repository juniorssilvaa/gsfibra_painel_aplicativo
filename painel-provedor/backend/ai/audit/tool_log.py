"""Audit log de execução de tools."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from ai.audit.trace import log_tool_call

logger = logging.getLogger(__name__)


class ToolCallLog:
    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def start(self, name: str, arguments: Optional[Dict] = None) -> float:
        return time.perf_counter()

    def finish(
        self,
        *,
        name: str,
        arguments: Optional[Dict] = None,
        result: Optional[Dict] = None,
        started_at: float,
        conversation_id: Optional[int] = None,
        provedor_id: Optional[int] = None,
        blocked: bool = False,
        block_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        entry = {
            "tool": name,
            "elapsed_ms": elapsed_ms,
            "success": bool((result or {}).get("success")) if result else False,
            "blocked": blocked,
            "block_reason": block_reason,
            "conversation_id": conversation_id,
            "provedor_id": provedor_id,
            "cached": bool((result or {}).get("cached")),
            "arguments": arguments or {},
        }
        self.calls.append(entry)

        log_tool_call(
            name=name,
            arguments=arguments,
            result=result,
            elapsed_ms=elapsed_ms,
            blocked=blocked,
            block_reason=block_reason,
        )
        logger.info(
            "[AI_AUDIT] tool=%s success=%s blocked=%s elapsed_ms=%s conv=%s",
            name,
            entry["success"],
            blocked,
            elapsed_ms,
            conversation_id,
        )
        return entry

    def summary(self) -> Dict[str, Any]:
        return {
            "tools": [c["tool"] for c in self.calls],
            "total_ms": round(sum(c.get("elapsed_ms", 0) for c in self.calls), 1),
            "calls": self.calls,
        }
