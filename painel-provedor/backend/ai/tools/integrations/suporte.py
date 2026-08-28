"""Tools ERP — domínio suporte técnico."""

from ai.tools.integrations._helpers import call_integration


def verificar_manutencao(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="verificar_manutencao",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def verificar_acesso(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="verificar_acesso",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def abrir_chamado(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="abrir_chamado",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )
