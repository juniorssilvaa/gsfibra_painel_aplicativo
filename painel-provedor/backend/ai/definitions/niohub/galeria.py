"""Definitions NioHub — Galeria de imagens."""

from ai.registry.tool_registry import register_tool
from ai.tools.niohub.galeria import enviar_imagens_galeria


def register():
    register_tool(
        name="enviar_imagens_galeria",
        handler=enviar_imagens_galeria,
        description=(
            "Apresenta planos ao cliente: imagem da Galeria ({planos}) e/ou texto da aba Planos. "
            "SEMPRE chame ao falar de planos/produtos/ofertas (tag='planos'). "
            "O servidor alterna imagem e texto quando os dois existem "
            "(nunca fica so em imagem, salvo regra na base de conhecimento pedindo somente imagem). "
            "Se o cliente pedir 'em texto', a tool devolve modo=texto — descreva planos_texto. "
            "Se modo=imagem, so 1 frase curta (nao repita o catalogo)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": (
                        'Variavel da galeria. Padrao "planos" / "{planos}".'
                    ),
                },
                "legenda": {
                    "type": "string",
                    "description": "Legenda opcional (so quando houver envio de imagem).",
                },
            },
            "required": [],
        },
        tags=["galeria", "niohub", "vendas", "planos"],
        permissions=["alteracao"],
        source="niohub",
        aliases=["enviar_imagem_galeria", "enviar_galeria"],
    )
