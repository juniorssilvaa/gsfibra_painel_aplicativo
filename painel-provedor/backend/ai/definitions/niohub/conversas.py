"""Definitions NioHub — conversas."""

from ai.registry.tool_registry import register_tool
from ai.tools.niohub.conversas import (
    buscar_conversas,
    transferir_conversa,
    transferir_inteligente,
)


def register():
    register_tool(
        name="transferir_conversa",
        handler=transferir_conversa,
        description="Transfere a conversa para uma equipe do NioHub.",
        parameters={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "integer"},
                "equipe_nome": {"type": "string"},
                "motivo": {"type": "string"},
            },
            "required": ["conversation_id", "equipe_nome", "motivo"],
        },
        tags=["conversas", "niohub", "atendimento"],
        permissions=["alteracao"],
        source="niohub",
        aliases=["executar_transferencia_conversa"],
    )
    register_tool(
        name="transferir_inteligente",
        handler=transferir_inteligente,
        description="Analisa a conversa e transfere automaticamente para a equipe mais adequada.",
        parameters={
            "type": "object",
            "properties": {"conversation_id": {"type": "integer"}},
            "required": ["conversation_id"],
        },
        tags=["conversas", "niohub"],
        permissions=["alteracao"],
        source="niohub",
        aliases=["transferir_conversa_inteligente"],
    )
    register_tool(
        name="buscar_conversas",
        handler=buscar_conversas,
        description="Lista conversas ativas do provedor no NioHub.",
        parameters={"type": "object", "properties": {}, "required": []},
        tags=["conversas", "niohub"],
        permissions=["consulta"],
        source="niohub",
        aliases=["buscar_conversas_ativas"],
    )
