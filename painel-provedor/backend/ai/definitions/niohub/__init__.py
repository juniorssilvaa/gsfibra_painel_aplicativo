"""Auto-registro das definitions NioHub (acoes internas do painel)."""

from ai.definitions.niohub import asaas_fatura, atendimento, conversas, equipes, galeria, horario, tickets


def register_all():
    equipes.register()
    conversas.register()
    atendimento.register()
    horario.register()
    tickets.register()
    galeria.register()
    asaas_fatura.register()
