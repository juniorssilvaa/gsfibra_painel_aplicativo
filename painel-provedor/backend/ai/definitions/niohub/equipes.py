"""Definitions NioHub — equipes."""

from ai.registry.tool_registry import register_tool
from ai.tools.niohub.equipes import buscar_equipes, buscar_membro_equipe


def register():
    register_tool(
        name="buscar_equipes",
        handler=buscar_equipes,
        description="Lista equipes disponiveis do provedor no NioHub para transferencia.",
        parameters={"type": "object", "properties": {}, "required": []},
        tags=["equipes", "niohub"],
        permissions=["consulta"],
        source="niohub",
        aliases=["buscar_equipes_disponiveis"],
    )
    register_tool(
        name="buscar_membro_equipe",
        handler=buscar_membro_equipe,
        description="Busca membros disponiveis de uma equipe no NioHub.",
        parameters={
            "type": "object",
            "properties": {
                "nome_equipe": {"type": "string", "description": "Nome da equipe"},
            },
            "required": ["nome_equipe"],
        },
        tags=["equipes", "niohub"],
        permissions=["consulta"],
        source="niohub",
        aliases=["buscar_membro_disponivel_equipe"],
    )
