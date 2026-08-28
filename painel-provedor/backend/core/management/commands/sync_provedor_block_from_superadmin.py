"""Sincroniza is_active local com o estado do provedor no superadmin."""
from django.core.management.base import BaseCommand

from core.login_provedor_access import (
    collect_user_provedores,
    refresh_provedores_block_from_superadmin,
    resolve_central_provedor_id,
)
from core.models import Provedor, User
from core.provedor_id_mapping import configured_central_provedor_id
from integrations.superadmin_notifier import (
    fetch_central_provedor_by_id,
    fetch_central_provedor_by_subdomain,
)


class Command(BaseCommand):
    help = 'Espelha suspensão do superadmin no provedor local (id central ≠ id local).'

    def add_arguments(self, parser):
        parser.add_argument('--provedor-id', type=int, help='Id local do provedor (default: todos)')
        parser.add_argument('--user-id', type=int, help='Sincronizar via utilizador (FK/M2M)')

    def handle(self, *args, **options):
        central_id = configured_central_provedor_id() or resolve_central_provedor_id()
        self.stdout.write(f'Id central (superadmin): {central_id or "não configurado"}')

        central = fetch_central_provedor_by_subdomain()
        if not central and central_id:
            central = fetch_central_provedor_by_id(central_id)
        if central:
            self.stdout.write(
                f"Superadmin: id={central.get('provedor_id')} "
                f"is_active={central.get('is_active')} status={central.get('status')!r}"
            )
        else:
            self.stdout.write(self.style.WARNING(
                'Não foi possível consultar o superadmin (401 = ADMIN_WEBHOOK_SECRET errado; '
                'ou configure SUPERADMIN_PROVIDER_TOKEN).'
            ))

        if options.get('user_id'):
            user = User.objects.filter(id=options['user_id']).first()
            if not user:
                self.stderr.write(f'Utilizador {options["user_id"]} não encontrado.')
                return
            provedores = collect_user_provedores(user)
        elif options.get('provedor_id'):
            p = Provedor.objects.filter(id=options['provedor_id']).first()
            provedores = [p] if p else []
        else:
            provedores = list(Provedor.objects.all())

        if not provedores:
            self.stderr.write('Nenhum provedor encontrado.')
            return

        refresh_provedores_block_from_superadmin(provedores, use_cache=False)

        for p in provedores:
            p.refresh_from_db(fields=['is_active', 'block_reason'])
            state = 'ATIVO' if p.is_active else 'SUSPENSO'
            self.stdout.write(
                f'Local id={p.id} ({p.nome}): {state}'
                + (f' — {p.block_reason}' if p.block_reason else '')
            )
