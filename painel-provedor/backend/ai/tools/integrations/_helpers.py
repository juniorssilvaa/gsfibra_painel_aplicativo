"""Helpers compartilhados das tools de integrações externas."""


def call_integration(*, actions, provedor, name: str, arguments, contexto, conversation_id):
    """Despacha para o runtime da integração configurada (hoje: SGP)."""
    args = dict(arguments or {})
    args.update({"provedor_id": provedor.id, "conversation_id": conversation_id})
    return actions.execute_integration_function(provedor, name, args, contexto)
