from django.core.management.base import BaseCommand
from django.db import connection

from core.models import User
from core.postgres_sequences import repair_model_pk_sequence


class Command(BaseCommand):
    help = (
        "Realinha a sequência PostgreSQL de core_user.id após importação com IDs fixos "
        "(corrige IntegrityError duplicate key em novos usuários)."
    )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stdout.write(self.style.WARNING("Este comando só se aplica a PostgreSQL."))
            return
        if repair_model_pk_sequence(User):
            self.stdout.write(self.style.SUCCESS("Sequência de core_user.id atualizada com sucesso."))
        else:
            self.stdout.write(self.style.ERROR("Não foi possível atualizar a sequência (veja os logs)."))
