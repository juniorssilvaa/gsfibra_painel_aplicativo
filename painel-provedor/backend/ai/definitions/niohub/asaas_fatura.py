"""Definitions NioHub — faturas Asaas (suporte da plataforma)."""

from ai.registry.tool_registry import register_tool
from ai.tools.niohub.asaas_fatura import buscar_faturas_asaas, enviar_fatura_asaas


def register():
    register_tool(
        name="buscar_faturas_asaas",
        handler=buscar_faturas_asaas,
        description=(
            "Busca no Asaas as faturas/cobranças do provedor pelo CPF ou CNPJ. "
            "Use quando o provedor pedir fatura, boleto, segunda via, PIX ou comprovante "
            "da assinatura NioHub (plataforma). NÃO use para fatura de assinante de internet/ERP. "
            "Retorna cliente e lista de cobranças em aberto/vencidas. "
            "Depois de listar, peça qual fatura enviar (ou confirme se houver só uma) "
            "e chame enviar_fatura_asaas."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cpf_cnpj": {
                    "type": "string",
                    "description": "CPF ou CNPJ do provedor (somente números ou formatado).",
                },
                "customer_id": {
                    "type": "string",
                    "description": "ID do cliente Asaas (obrigatório se houver mais de um cadastro).",
                },
                "incluir_pagas": {
                    "type": "boolean",
                    "description": "Se true, inclui algumas faturas pagas recentes.",
                },
            },
            "required": ["cpf_cnpj"],
        },
        tags=["asaas", "financeiro", "niohub", "support"],
        permissions=["consulta"],
        source="niohub",
    )
    register_tool(
        name="enviar_fatura_asaas",
        handler=enviar_fatura_asaas,
        description=(
            "Envia na conversa a fatura/cobrança Asaas do NioHub (PIX e/ou boleto). "
            "Use após buscar_faturas_asaas, com o payment_id escolhido. "
            "Padrão: ambos (PIX + boleto quando disponíveis)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "payment_id": {
                    "type": "string",
                    "description": "ID da cobrança no Asaas (ex.: pay_...).",
                },
                "cpf_cnpj": {
                    "type": "string",
                    "description": "CPF/CNPJ já consultado (recomendado para validação).",
                },
                "tipo_pagamento": {
                    "type": "string",
                    "enum": ["pix", "boleto", "ambos"],
                    "description": "Padrão ambos.",
                },
            },
            "required": ["payment_id"],
        },
        tags=["asaas", "financeiro", "niohub", "support"],
        permissions=["alteracao"],
        source="niohub",
    )
