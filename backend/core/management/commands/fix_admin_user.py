from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Provedor

User = get_user_model()

class Command(BaseCommand):
    help = 'Garante que o usuário admin seja superadmin e não seja resetado'

    def handle(self, *args, **options):
        username = 'admin'
        try:
            user = User.objects.get(username=username)
            user.user_type = 'superadmin'
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Usuário "{username}" atualizado para superadmin com sucesso!'))
            
            # Associar a todos os provedores existentes para garantir acesso total
            provedores = Provedor.objects.all()
            for provedor in provedores:
                if user not in provedor.admins.all():
                    provedor.admins.add(user)
                    self.stdout.write(self.style.SUCCESS(f'✓ Usuário "{username}" associado ao provedor "{provedor.nome}"'))
                    
        except User.DoesNotExist:
            self.stdout.write(self.style.WARNING(f'! Usuário "{username}" não encontrado. Criando...'))
            user = User.objects.create_superuser(
                username=username,
                email='admin@niohub.com.br',
                password='admin', # Senha padrão inicial, deve ser alterada
                user_type='superadmin'
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Usuário "{username}" criado como superadmin com sucesso!'))
            
            # Associar a todos os provedores
            provedores = Provedor.objects.all()
            for provedor in provedores:
                provedor.admins.add(user)
