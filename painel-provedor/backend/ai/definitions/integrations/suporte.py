"""Definitions ERP — suporte."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.suporte import (
    abrir_chamado,
    consultar_chamados,
    verificar_acesso,
    verificar_manutencao,
)


def register():
    register_tool(
        name="verificar_manutencao",
        handler=verificar_manutencao,
        description=(
            "Verifica manutencao programada no ERP. "
            "So informe manutencao ao cliente se tem_manutencao=true. "
            "Se tem_manutencao=false, NUNCA mencione manutencao."
        ),
        parameters={
            "type": "object",
            "properties": {"cpf_cnpj": {"type": "string"}},
            "required": ["cpf_cnpj"],
        },
        tags=["suporte", "integrations", "erp"],
        erp=["sgp", "ixc"],
        permissions=["consulta"],
        source="integrations",
        aliases=["verificar_manutencao_sgp"],
    )
    register_tool(
        name="verificar_acesso",
        handler=verificar_acesso,
        description=(
            "Verifica se a CONEXAO esta Online, Offline ou Manutencao. "
            "Parametro contrato = contrato_id retornado por buscar_cliente, NUNCA o CPF. "
            "Se Offline: siga a nota da tool (informe offline; depois 1 pergunta por msg: "
            "ligado na tomada → LED/LOS → diagnostico). "
            "LED vermelho/LOS: NÃO abra chamado nem transfira so por isso; "
            "verifique manutencao e continue o suporte. "
            "Nunca invente manutencao; nunca reinicio antes de confirmar ligado."
        ),
        parameters={
            "type": "object",
            "properties": {"contrato": {"type": "string"}},
            "required": ["contrato"],
        },
        tags=["suporte", "integrations", "erp"],
        erp=["sgp", "ixc"],
        permissions=["consulta"],
        source="integrations",
        aliases=["verificar_acesso_sgp"],
    )
    register_tool(
        name="consultar_chamados",
        handler=consultar_chamados,
        description=(
            "Consulta no ERP se o contrato ja tem chamado em andamento (situacao Aberta ou Pendente). "
            "Use quando o cliente pedir visita tecnica, perguntar do chamado dele, ou antes de abrir chamado. "
            "Parametro contrato = contrato_id do buscar_cliente/selecionar_contrato, NUNCA o CPF. "
            "tem_chamado_aberto=true: informe protocolo/situacao e NAO abra outro. "
            "tem_chamado_aberto=false: se o cliente pediu visita tecnica, chame abrir_chamado; "
            "se ele so queria saber do chamado, informe e pergunte se deseja abrir. "
            "Nunca mencione chamados encerrados."
        ),
        parameters={
            "type": "object",
            "properties": {"contrato": {"type": "string"}},
            "required": ["contrato"],
        },
        tags=["suporte", "integrations", "erp"],
        erp=["sgp"],
        permissions=["consulta"],
        source="integrations",
    )
    register_tool(
        name="abrir_chamado",
        handler=abrir_chamado,
        description=(
            "Abre chamado tecnico no ERP. "
            "Problema de internet: somente apos diagnostico com o cliente "
            "(CPF, contrato escolhido, verificar_manutencao e verificar_acesso). "
            "Pedido de visita tecnica: abra direto apos o contrato escolhido e consultar_chamados sem chamado aberto "
            "(sem diagnostico); no conteudo descreva o pedido e a data/periodo que o cliente pediu. "
            "Se o cliente ja tiver chamado Aberto/Pendente, a tool NAO abre outro e retorna o protocolo existente. "
            "Use o contrato_id retornado por buscar_cliente/selecionar_contrato, NUNCA o CPF/CNPJ "
            "e NUNCA invente um numero de contrato. "
            "Nao use so porque o cliente mencionou LED vermelho ou enviou foto do modem."
        ),
        parameters={
            "type": "object",
            "properties": {
                "contrato": {"type": "string"},
                "conteudo": {"type": "string"},
            },
            "required": ["contrato", "conteudo"],
        },
        tags=["suporte", "integrations", "erp"],
        erp=["sgp", "ixc"],
        permissions=["alteracao"],
        source="integrations",
        aliases=["criar_chamado_tecnico"],
    )
