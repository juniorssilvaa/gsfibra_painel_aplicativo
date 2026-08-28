"""Contexto de conversa injetado no system prompt (separado do Prompt Base)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from django.utils import timezone


def build_conversation_context(
    *,
    provedor,
    conversation_state: Optional[Dict[str, Any]] = None,
    conversation_id: Optional[int] = None,
    contact_phone: str = "unknown",
    channel: str = "wa",
    ai_conversation_id: str = "",
    protocolo: Optional[str] = None,
    protocol_source: Optional[str] = None,
    informar_protocolo_primeira_resposta: bool = False,
) -> Dict[str, Any]:
    state = conversation_state or {}
    return {
        "ai_conversation_id": ai_conversation_id,
        "conversation_id": conversation_id,
        "provedor_id": getattr(provedor, "id", None),
        "provedor_nome": getattr(provedor, "nome", None),
        "telefone": contact_phone,
        "canal": channel,
        "fluxo_atual": state.get("flow") or "NONE",
        "step_atual": state.get("step") or "INICIAL",
        "original_intent": state.get("original_intent") or "NONE",
        "dados_confirmados": bool(state.get("dados_confirmados")),
        "protocolo_atendimento": protocolo,
        "protocol_source": protocol_source,
        "informar_protocolo_primeira_resposta": informar_protocolo_primeira_resposta,
        "timestamp": timezone.now().isoformat(),
    }


def as_prompt_block(ctx: Dict[str, Any]) -> str:
    lines = ["# CONTEXTO DA CONVERSA", json.dumps(ctx, indent=2, ensure_ascii=False, default=str)]
    proto = ctx.get("protocolo_atendimento")
    if proto:
        lines.append(
            "# PROTOCOLO DE ATENDIMENTO\n"
            f"- Protocolo atual: {proto}\n"
            + (
                "- OBRIGATÓRIO na primeira resposta: informe este protocolo ao cliente "
                f'(ex.: "Seu protocolo de atendimento é {proto}").'
                if ctx.get("informar_protocolo_primeira_resposta")
                else "- Se o protocolo mudar (chamado SGP), informe o novo número ao cliente."
            )
        )
    return "\n".join(lines)
