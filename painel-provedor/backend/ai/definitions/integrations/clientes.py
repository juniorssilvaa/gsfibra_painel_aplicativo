"""Definitions ERP — clientes."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.clientes import buscar_cliente, selecionar_contrato


def register():
    register_tool(
        name="buscar_cliente",
        handler=buscar_cliente,
        description=(
            "Busca cliente no ERP por CPF/CNPJ (cliente ja existente). "
            "Use para fatura, boleto, meu plano, suporte, liberacao, chamado, "
            "e tambem para troca de senha/nome do Wi-Fi (retorna e salva pppoe_login). "
            "Em suporte de internet ou Wi-Fi: peca CPF/CNPJ para localizar o cadastro/conexao — "
            "nao diga 'verificar status do contrato'. "
            "Nao use em contratacao/venda de plano novo — transfira para COMERCIAL. "
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
            "properties": {"cpf_cnpj": {"type": "string"}},
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
            "Use quando o cliente confirmar (sim, esta certo, pode) ou escolher o contrato "
            "(numero da lista 1, 2, 3... ou id do contrato, ex.: 10624). "
            "Na resposta ao cliente: use o nome do titular e diga que ele selecionou o contrato X. "
            "Em seguida JA execute o pedido original (fatura, suporte, Wi-Fi, desbloqueio). "
            "Se a intencao era fatura/boleto, a fatura do contrato escolhido e gerada em seguida. "
            "Nao invente a escolha."
        ),
        parameters={
            "type": "object",
            "properties": {
                "escolha": {
                    "type": "string",
                    "description": "Numero da lista (1, 2, 3...) ou id do contrato escolhido.",
                },
                "contrato_id": {
                    "type": "string",
                    "description": "Id do contrato, se o cliente informou o numero do contrato.",
                },
            },
            "required": ["escolha"],
        },
        tags=["cliente", "integrations", "erp", "contrato"],
        erp=["sgp", "ixc"],
        permissions=["consulta"],
        source="integrations",
        aliases=["escolher_contrato"],
    )
