"""Contexto do cliente (dados confirmados na memória / ERP)."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def build_customer_context(conversation_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    state = conversation_state or {}
    return {
        "pedido_cliente": state.get("pedido_cliente"),
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
        "chamados_consultados_contrato": state.get("chamados_consultados_contrato"),
        "chamados_em_andamento": state.get("chamados_em_andamento"),
        "chamado_aberto_protocolo": state.get("chamado_aberto_protocolo"),
        "cidade": state.get("cidade") or state.get("endereco_cidade"),
        "tags": state.get("tags") or [],
    }


def as_prompt_block(ctx: Dict[str, Any]) -> str:
    # Só injeta se houver algum dado útil
    if not any(v not in (None, "", [], False) for k, v in ctx.items() if k != "tags"):
        if not ctx.get("tags"):
            return ""
    block = "# CONTEXTO DO CLIENTE (memoria Redis desta conversa)\n" + json.dumps(
        ctx, indent=2, ensure_ascii=False, default=str
    )
    block += (
        "\n# COMO USAR A MEMORIA\n"
        "Tudo acima ja foi perguntado, respondido ou consultado nesta conversa. "
        "Nao pergunte de novo nem refaca consultas cujo resultado ja esta aqui, "
        "a menos que o cliente mude de assunto, de contrato ou peca para verificar novamente. "
        "pedido_cliente e o que voce mesmo entendeu antes; confira com a mensagem atual se o cliente "
        "continua no mesmo pedido ou mudou, e ao chamar buscar_cliente/selecionar_contrato "
        "envie pedido_cliente atualizado."
    )
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
            "precisa_confirmar_dados=true: mostre os contratos e peca UMA vez se os dados estao corretos. "
            "Com 2+ contratos, ainda NAO pergunte qual contrato. "
            "Interprete a resposta do cliente em relacao a sua pergunta: se ele confirmou, "
            "chame selecionar_contrato imediatamente."
        )
    return block
