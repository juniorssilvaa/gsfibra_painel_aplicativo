"""Contexto do cliente (dados confirmados na memória / ERP)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def build_customer_context(conversation_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = conversation_state or {}
    return {
        "cpf_cnpj": state.get("cpf_cnpj"),
        "nome_cliente": state.get("nome_cliente"),
        "contrato_id": state.get("contrato_id"),
        "contrato_escolhido": bool(state.get("contrato_escolhido")),
        "dados_confirmados": bool(state.get("dados_confirmados")),
        "precisa_escolher_contrato": bool(state.get("precisa_escolher_contrato")),
        "precisa_confirmar_dados": bool(state.get("precisa_confirmar_dados")),
        "quantidade_contratos": len(state.get("contratos") or []) or None,
        "pppoe_login": state.get("pppoe_login") or state.get("servico_login"),
        "plano": state.get("servico_plano"),
        "is_suspenso": state.get("is_suspenso"),
        "contrato_status": state.get("contrato_status_display"),
        "motivo_status": state.get("motivo_status"),
        "fatura_enviada": state.get("fatura_enviada"),
        "cidade": state.get("cidade") or state.get("endereco_cidade"),
        "tags": state.get("tags") or [],
    }


def as_prompt_block(ctx: Dict[str, Any]) -> str:
    # Só injeta se houver algum dado útil
    if not any(v not in (None, "", [], False) for k, v in ctx.items() if k != "tags"):
        if not ctx.get("tags"):
            return ""
    block = "# CONTEXTO DO CLIENTE\n" + json.dumps(ctx, indent=2, ensure_ascii=False, default=str)
    if ctx.get("contrato_escolhido"):
        block += (
            "\n# REGRA DE MEMORIA (Redis)\n"
            "contrato_escolhido=true: os dados do cadastro JA foram confirmados nesta conversa. "
            "NUNCA peca o cliente confirmar nome/contrato/endereco de novo. Prossiga com a acao."
        )
    elif ctx.get("precisa_escolher_contrato") or (
        ctx.get("dados_confirmados") and not ctx.get("contrato_escolhido")
    ):
        block += (
            "\n# REGRA DE MEMORIA (Redis)\n"
            "dados_confirmados=true / precisa_escolher_contrato=true: "
            "NAO peca confirmar nome/endereco de novo. "
            "Pergunte com naturalidade para qual contrato e o atendimento. "
            "Quando o cliente escolher, chame selecionar_contrato."
        )
    elif ctx.get("precisa_confirmar_dados"):
        block += (
            "\n# REGRA DE MEMORIA (Redis)\n"
            "precisa_confirmar_dados=true: mostre a lista de contratos e peca UMA vez se os dados estao corretos. "
            "Com 2+ contratos, ainda NAO pergunte qual contrato. "
            "Se a mensagem atual for confirmacao (sim/esta certo), chame selecionar_contrato imediatamente."
        )
    return block
