"""Definitions ERP — suporte."""

from ai.registry.tool_registry import register_tool
from ai.tools.integrations.suporte import abrir_chamado, verificar_acesso, verificar_manutencao


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
        name="abrir_chamado",
        handler=abrir_chamado,
        description=(
            "Abre chamado tecnico no ERP somente apos diagnostico com o cliente "
            "(CPF, contrato escolhido, verificar_manutencao e verificar_acesso). "
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
