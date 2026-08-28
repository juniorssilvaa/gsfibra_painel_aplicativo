"""Tools ERP — domínio financeiro."""

from ai.tools.integrations._helpers import call_integration


def gerar_fatura(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    """Gera e envia fatura (PIX por padrao; boleto/ambos se KB ou parametro pedirem)."""
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="gerar_fatura",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )


def liberar_confianca(*, provedor, arguments, contexto, conversation_id, actions, **_kw):
    """Desbloqueia contrato suspenso em confiança."""
    return call_integration(
        actions=actions,
        provedor=provedor,
        name="liberar_confianca",
        arguments=arguments,
        contexto=contexto,
        conversation_id=conversation_id,
    )
