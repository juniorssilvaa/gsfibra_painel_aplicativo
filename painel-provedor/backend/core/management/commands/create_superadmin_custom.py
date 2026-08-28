from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Cria ou atualiza um superadmin'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default='Junior', help='Nome de usuário')
        parser.add_argument('--password', type=str, default='Senfim01@', help='Senha')
        parser.add_argument('--user-type', type=str, default='superadmin', help='Tipo de usuário')

    def handle(self, *args, **options):
        username = options['username']
        password = options['password']
        user_type = options['user_type']
        
        try:
            user = User.objects.get(username=username)
            user.set_password(password)
            user.user_type = user_type
            user.is_staff = True
            user.is_superuser = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'✓ Usuário "{username}" atualizado com sucesso!'))
        except User.DoesNotExist:
            user = User.objects.create_user(
                username=username,
                password=password,
                user_type=user_type,
                is_staff=True,
                is_superuser=True
            )
            self.stdout.write(self.style.SUCCESS(f'✓ Usuário "{username}" criado com sucesso!'))
        
        self.stdout.write(self.style.SUCCESS(f'\nCredenciais:'))
        self.stdout.write(self.style.SUCCESS(f'Usuário: {username}'))
        self.stdout.write(self.style.SUCCESS(f'Senha: {password}'))
        self.stdout.write(self.style.SUCCESS(f'Tipo: {user_type}'))






