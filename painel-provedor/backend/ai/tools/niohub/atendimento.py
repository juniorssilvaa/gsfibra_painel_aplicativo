"""Tools NioHub — atendimento (encerrar, resumo interno)."""

from ai.tools.niohub._helpers import call_niohub


def encerrar_atendimento(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_niohub(
        actions=actions,
        provedor=provedor,
        name="encerrar_atendimento",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def criar_resumo(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_niohub(
        actions=actions,
        provedor=provedor,
        name="criar_resumo",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )
