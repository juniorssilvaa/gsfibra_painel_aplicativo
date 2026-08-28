"""Definitions ERP — financeiro."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.financeiro import gerar_fatura, liberar_confianca


def register():
    register_tool(
        name="gerar_fatura",
        handler=gerar_fatura,
        description=(
            "Gera e envia a fatura ao cliente do CONTRATO ja escolhido. "
            "Padrao: PIX. "
            "Se a base de conhecimento do provedor pedir fatura completa / boleto e PIX / ambas as formas, "
            "chame com tipo_pagamento=ambos (envia boleto + PIX como no chatbot). "
            "Valores: pix | boleto | ambos. "
            "Se o cliente tem varios contratos, so use depois de selecionar_contrato. "
            "Nao diga que nao ha fatura sem ter o contrato escolhido."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cpf_cnpj": {"type": "string"},
                "contrato_id": {
                    "type": "string",
                    "description": "Id do contrato escolhido (obrigatorio se houver varios).",
                },
                "tipo_pagamento": {
                    "type": "string",
                    "enum": ["pix", "boleto", "ambos"],
                    "description": (
                        "Forma de pagamento a enviar. Padrao pix. "
                        "Use ambos quando a base de conhecimento pedir boleto e PIX / fatura completa."
                    ),
                },
            },
            "required": ["cpf_cnpj"],
        },
        tags=["financeiro", "integrations", "erp", "fatura"],
        erp=["sgp", "ixc"],
        permissions=["consulta", "alteracao"],
        source="integrations",
        aliases=["gerar_fatura_completa"],
    )
    register_tool(
        name="liberar_confianca",
        handler=liberar_confianca,
        description="Desbloqueia em confianca um contrato suspenso.",
        parameters={
            "type": "object",
            "properties": {
                "contrato": {"type": "string"},
                "cpf_cnpj": {"type": "string"},
                "conteudo": {"type": "string"},
            },
            "required": ["contrato"],
        },
        tags=["financeiro", "integrations", "erp"],
        erp=["sgp", "ixc"],
        permissions=["alteracao"],
        source="integrations",
        aliases=["liberar_por_confianca"],
    )
