"""Tools NioHub — conversas (transferência e listagem)."""

from ai.tools.niohub._helpers import call_niohub


def transferir_conversa(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_niohub(
        actions=actions,
        provedor=provedor,
        name="transferir_conversa",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def transferir_inteligente(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_niohub(
        actions=actions,
        provedor=provedor,
        name="transferir_inteligente",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def buscar_conversas(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_niohub(
        actions=actions,
        provedor=provedor,
        name="buscar_conversas",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )
