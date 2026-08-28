"""
Utilizador de suporte Niohub no painel do **provedor** (tenant).

- user_type = admin (não «superadmin») para NÃO redireccionar para o app Superadmin.
- Liga-se ao Provedor desta stack com a seguinte ordem de prioridade:
    1. SUPERADMIN_PROVEDOR_ID (variável de ambiente explícita)
    2. Lookup no superadmin pelo subdomínio (SUPERADMIN_ID_PROVEDOR_API, etc.)
    3. Provedor com maior id no banco local (heurística)
    4. Cria um Provedor placeholder se nenhum existir
- Entra no M2M admins do Provedor.
- Credenciais: niohub / Semfim01@ (ou NIOHUB_SUPPORT_PASSWORD).
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.models import Provedor

User = get_user_model()

SUPPORT_USERNAME = 'niohub'
DEFAULT_PASSWORD = 'Semfim01@'


def _resolve_or_create_provedor():
    # 1. Variável de ambiente explícita (definida pelo superadmin ao provisionar)
    raw = os.environ.get('SUPERADMIN_PROVEDOR_ID', '').strip()
    if raw:
        try:
            pid = int(raw)
            p = Provedor.objects.filter(id=pid).first()
            if p:
                return p, False
        except ValueError:
            pass

    # 2. Consultar o superadmin pelo subdomínio (fonte de verdade)
    try:
        from core.support_account import resolve_provedor_id_from_superadmin
        pid = resolve_provedor_id_from_superadmin()
        if pid:
            p = Provedor.objects.filter(id=pid).first()
            if not p:
                nome = os.environ.get('NIOHUB_DEFAULT_PROVEDOR_NOME', 'Provedor').strip() or 'Provedor'
                p = Provedor.objects.create(id=pid, nome=nome)
            return p, False
    except Exception:
        pass

    # 3. Usar o Provedor com MAIOR id — o real criado pelo superadmin (não o placeholder)
    p = Provedor.objects.order_by('-id').first()
    if p:
        return p, False

    # 4. Não existe nenhum Provedor — criar um mínimo (placeholder)
    #    Quando o superadmin criar o Provedor real, o webhook sync-niohub irá corrigi-lo.
    nome = os.environ.get('NIOHUB_DEFAULT_PROVEDOR_NOME', 'Provedor').strip() or 'Provedor'
    p = Provedor.objects.create(nome=nome)
    return p, True


class Command(BaseCommand):
    help = 'Cria ou actualiza o utilizador de suporte niohub (admin neste painel do provedor).'

    def handle(self, *args, **options):
        password = os.environ.get('NIOHUB_SUPPORT_PASSWORD', DEFAULT_PASSWORD).strip() or DEFAULT_PASSWORD

        try:
            provedor, created = _resolve_or_create_provedor()
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f'Erro ao resolver/criar Provedor: {exc}')
            )
            return

        if created:
            self.stdout.write(
                self.style.WARNING(
                    f'Nenhum Provedor encontrado — criado Provedor id={provedor.id} («{provedor.nome}»). '
                    'Configure-o via painel admin.'
                )
            )

        user = User.objects.filter(username__iexact=SUPPORT_USERNAME).first()
        if user and user.username != SUPPORT_USERNAME:
            user.username = SUPPORT_USERNAME

        if user:
            user.set_password(password)
            user.email = user.email or 'suporte@niohub.com.br'
            user.user_type = 'admin'
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.provedor = provedor
            user.save()
        else:
            user = User.objects.create(
                username=SUPPORT_USERNAME,
                email='suporte@niohub.com.br',
                user_type='admin',
                is_staff=True,
                is_superuser=True,
                is_active=True,
                provedor=provedor,
            )
            user.set_password(password)
            user.save()

        if user not in provedor.admins.all():
            provedor.admins.add(user)
            self.stdout.write(
                self.style.SUCCESS(
                    f'niohub associado aos admins do provedor «{provedor.nome}» (id={provedor.id}).'
                )
            )
        else:
            self.stdout.write(f'niohub já em admins do provedor «{provedor.nome}».')

        self.stdout.write(self.style.SUCCESS(f'Utilizador «{SUPPORT_USERNAME}» pronto (admin neste painel).'))
