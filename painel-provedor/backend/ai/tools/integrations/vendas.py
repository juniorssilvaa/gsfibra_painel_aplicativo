"""Tools ERP — domínio vendas."""

from ai.tools.integrations._helpers import call_integration


def consulta_viabilidade(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="consulta_viabilidade",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )
