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
    origem_anuncio: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    state = conversation_state or {}
    ctx = {
        "ai_conversation_id": ai_conversation_id,
        "conversation_id": conversation_id,
        "provedor_id": getattr(provedor, "id", None),
        "provedor_nome": getattr(provedor, "nome", None),
        "telefone": contact_phone,
        "canal": channel,
        "step_atual": state.get("step") or "INICIAL",
        "dados_confirmados": bool(state.get("dados_confirmados")),
        "protocolo_atendimento": protocolo,
        "protocol_source": protocol_source,
        "informar_protocolo_primeira_resposta": informar_protocolo_primeira_resposta,
        "timestamp": timezone.now().isoformat(),
    }
    if origem_anuncio:
        ctx["origem_anuncio"] = origem_anuncio
    return ctx


def as_prompt_block(ctx: Dict[str, Any]) -> str:
    lines = ["# CONTEXTO DA CONVERSA", json.dumps(ctx, indent=2, ensure_ascii=False, default=str)]
    if ctx.get("origem_anuncio"):
        lines.append(
            "# ORIGEM DO CLIENTE\n"
            "- O cliente iniciou esta conversa clicando no anúncio/publicação descrito em origem_anuncio. "
            "Use o título e o texto como contexto do interesse dele.\n"
            "- Preços, planos e condições só podem vir das tools e dos planos cadastrados; "
            "não prometa nada que esteja apenas no anúncio."
        )
    proto = ctx.get("protocolo_atendimento")
    if proto:
        lines.append(
            "# PROTOCOLO DE ATENDIMENTO\n"
            f"- Protocolo atual: {proto}\n"
            + (
                "- OBRIGATÓRIO na primeira resposta: informe este protocolo ao cliente, com suas palavras."
                if ctx.get("informar_protocolo_primeira_resposta")
                else "- Se o protocolo mudar (chamado SGP), informe o novo número ao cliente."
            )
        )
    return "\n".join(lines)
