"""Helpers das tools internas NioHub."""


def call_niohub(*, actions, provedor, name: str, arguments, contexto, conversation_id):
    return actions.execute_database_function(provedor, name, arguments or {}, contexto)
