"""Definitions ERP — clientes."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.clientes import buscar_cliente, selecionar_contrato

_PEDIDO_CLIENTE_PARAM = {
    "type": "string",
    "description": (
        "Resumo curto do que o cliente quer neste atendimento, como voce entendeu da conversa. "
        "Fica salvo na memoria (Redis) para nao perguntar de novo."
    ),
}


def register():
    register_tool(
        name="buscar_cliente",
        handler=buscar_cliente,
        description=(
            "Busca cliente no ERP por CPF/CNPJ (cliente ja existente). "
            "Use sempre que precisar do cadastro de quem ja e cliente (fatura, plano, suporte, liberacao, "
            "chamado/visita, Wi-Fi — retorna e salva pppoe_login). "
            "Nao use para quem ainda nao e cliente e quer contratar — transfira para o comercial. "
            "OBRIGATORIO apos o retorno: use APENAS mensagem_cliente_sugerida / contratos "
            "retornados pela tool (nome, id e endereco reais). "
            "Nunca invente contrato nem escreva placeholders. "
            "Sem sucesso da tool, peca CPF/CNPJ de novo. "
            "Com 1 contrato: peca confirmacao UMA vez e so entao prossiga. "
            "Com 2+ contratos: ETAPA 1 peca so se os dados estao corretos; "
            "quando confirmar, chame selecionar_contrato ('sim'); "
            "ETAPA 2 pergunte para qual contrato e o atendimento e chame selecionar_contrato de novo. "
            "Nao execute fatura/suporte antes da escolha final. "
            "Apos contrato_escolhido=true (Redis), NUNCA peca confirmacao de cadastro de novo."
        ),
        parameters={
            "type": "object",
            "properties": {
                "cpf_cnpj": {"type": "string"},
                "pedido_cliente": _PEDIDO_CLIENTE_PARAM,
            },
            "required": ["cpf_cnpj"],
        },
        tags=["cliente", "integrations", "erp"],
        erp=["sgp", "ixc"],
        permissions=["consulta"],
        source="integrations",
        aliases=["consultar_cliente_sgp"],
    )
    register_tool(
        name="selecionar_contrato",
        handler=selecionar_contrato,
        description=(
            "Confirma os dados do cliente ou o contrato escolhido. "
            "Use quando voce entender, pela resposta do cliente a sua pergunta, que ele confirmou os dados "
            "(escolha='sim') ou indicou um contrato (posicao na lista ou id). "
            "Depois JA execute, com a ferramenta certa, o que o cliente pediu (veja pedido_cliente) "
            "e responda com suas palavras. Nunca execute algo que ele nao pediu. "
            "Nao invente a escolha."
        ),
        parameters={
            "type": "object",
            "properties": {
                "escolha": {
                    "type": "string",
                    "description": (
                        "'sim' quando o cliente confirmou os dados; ou a posicao na lista (1, 2, 3...) "
                        "ou o id do contrato que ele escolheu."
                    ),
                },
                "contrato_id": {
                    "type": "string",
                    "description": "Id do contrato, se o cliente informou o numero do contrato.",
                },
                "pedido_cliente": _PEDIDO_CLIENTE_PARAM,
            },
            "required": ["escolha"],
        },
        tags=["cliente", "integrations", "erp", "contrato"],
        erp=["sgp", "ixc"],
        permissions=["consulta"],
        source="integrations",
        aliases=["escolher_contrato"],
    )
