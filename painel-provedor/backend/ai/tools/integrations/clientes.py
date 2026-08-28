"""Tools ERP — domínio clientes."""

from ai.tools.integrations._helpers import call_integration


def buscar_cliente(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    """Busca cliente no ERP por CPF/CNPJ."""
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="buscar_cliente",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def selecionar_contrato(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    """Confirma o contrato escolhido pelo cliente quando há mais de um."""
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="selecionar_contrato",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )
