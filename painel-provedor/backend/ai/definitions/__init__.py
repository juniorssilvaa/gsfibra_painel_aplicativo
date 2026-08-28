"""Definitions package — schemas e registro por domínio."""

from ai.definitions.tool_definitions import (
    build_tools_for_provedor,
    detect_erp,
    register_all_tools,
)

__all__ = [
    "build_tools_for_provedor",
    "detect_erp",
    "register_all_tools",
]
