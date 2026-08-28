from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from core.models import Provedor

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Cria ou atualiza um utilizador do painel com user_type=admin, "
        "ligado a um Provedor (FK + M2M admins). Uso típico no Swarm: "
        "docker exec -it <backend> python manage.py ensure_provider_admin"
    )

    def add_arguments(self, parser):
        parser.add_argument("--username", type=str, default="demo", help="Login")
        parser.add_argument("--password", type=str, default="demo", help="Senha")
        parser.add_argument(
            "--email",
            type=str,
            default="",
            help="E-mail (default: <username>@niohub.local)",
        )
        parser.add_argument(
            "--provedor-id",
            type=int,
            default=None,
            help="ID do Provedor; se omitido e existir só um, usa esse",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email = (options["email"] or "").strip() or f"{username}@niohub.local"
        provedor_id = options["provedor_id"]

        if provedor_id is not None:
            provedor = Provedor.objects.filter(id=provedor_id).first()
            if not provedor:
                self.stderr.write(self.style.ERROR(f"Provedor id={provedor_id} não encontrado."))
                return
        else:
            provedores = list(Provedor.objects.order_by("id"))
            if len(provedores) == 0:
                provedor = Provedor.objects.create(nome="Provedor inicial")
                self.stdout.write(
                    self.style.WARNING(f"Criado Provedor id={provedor.id} (não havia nenhum).")
                )
            elif len(provedores) == 1:
                provedor = provedores[0]
            else:
                self.stderr.write(
                    self.style.ERROR(
                        "Há vários provedores; passe --provedor-id. "
                        + ", ".join(f"{p.id}={p.nome!r}" for p in provedores[:20])
                    )
                )
                return

        user = User.objects.filter(username=username).first()
        if user:
            user.set_password(password)
            user.email = email
            user.user_type = "admin"
            user.is_staff = True
            user.is_superuser = False
            user.is_active = True
            user.provedor = provedor
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Utilizador "{username}" atualizado (admin).'))
        else:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                user_type="admin",
                is_staff=True,
                is_superuser=False,
                provedor=provedor,
            )
            self.stdout.write(self.style.SUCCESS(f'Utilizador "{username}" criado (admin).'))

        if user not in provedor.admins.all():
            provedor.admins.add(user)
            self.stdout.write(self.style.SUCCESS(f'Associado a admins do provedor "{provedor.nome}" (id={provedor.id}).'))
        else:
            self.stdout.write(f'Já em admins do provedor "{provedor.nome}" (id={provedor.id}).')
