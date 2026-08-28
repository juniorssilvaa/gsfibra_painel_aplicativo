"""Auto-registro das definitions de integrações externas."""

from ai.definitions.integrations import acs, clientes, financeiro, suporte, vendas


def register_all():
    clientes.register()
    financeiro.register()
    suporte.register()
    vendas.register()
    acs.register()
