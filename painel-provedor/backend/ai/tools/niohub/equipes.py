"""Tools NioHub — equipes."""

from ai.tools.niohub._helpers import call_niohub


def buscar_equipes(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_niohub(
        actions=actions,
        provedor=provedor,
        name="buscar_equipes",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def buscar_membro_equipe(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_niohub(
        actions=actions,
        provedor=provedor,
        name="buscar_membro_equipe",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )
