"""Definitions NioHub — atendimento."""

from ai.registry.tool_registry import register_tool
from ai.tools.niohub.atendimento import criar_resumo, encerrar_atendimento


def register():
    register_tool(
        name="encerrar_atendimento",
        handler=encerrar_atendimento,
        description=(
            "Encerra o atendimento atual no NioHub. "
            "Use quando o cliente agradecer, disser que vai aguardar (ex.: apos manutencao), "
            "que esta tudo certo ou que nao precisa de mais nada. "
            "Apos encerrar, faca despedida completa (agradeça o provedor; use nome do cliente se houver)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "motivo": {"type": "string", "description": "Motivo do encerramento"},
            },
            "required": ["motivo"],
        },
        tags=["atendimento", "niohub"],
        permissions=["alteracao"],
        source="niohub",
    )
    register_tool(
        name="criar_resumo",
        handler=criar_resumo,
        description=(
            "Cria resumo interno do atendimento (visivel so para atendentes). "
            "Use antes de transferir, com o que o cliente pediu e o diagnostico feito."
        ),
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "integer"},
                "resumo_texto": {"type": "string"},
            },
            "required": ["conversation_id", "resumo_texto"],
        },
        tags=["atendimento", "niohub"],
        permissions=["alteracao"],
        source="niohub",
        aliases=["criar_resumo_suporte"],
    )
