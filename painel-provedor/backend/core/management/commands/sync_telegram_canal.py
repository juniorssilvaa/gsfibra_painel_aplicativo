"""
Comando para sincronizar dados de um canal Telegram
Usage: python manage.py sync_telegram_canal <canal_id>
"""

import asyncio
from django.core.management.base import BaseCommand
from core.models import Canal
from core.telegram_service import telegram_service


class Command(BaseCommand):
    help = 'Sincroniza dados de um canal Telegram buscando informações em tempo real'

    def add_arguments(self, parser):
        parser.add_argument('canal_id', type=int, help='ID do canal a sincronizar')

    def handle(self, *args, **options):
        canal_id = options['canal_id']
        
        try:
            canal = Canal.objects.get(id=canal_id, tipo='telegram')
            self.stdout.write(f"\nCanal encontrado: {canal.nome}")
            self.stdout.write(f"   ID: {canal.id}")
            self.stdout.write(f"   API_ID: {canal.api_id}")
            self.stdout.write(f"   Phone: {canal.phone_number}")
            
            # Verificar dados_extras
            self.stdout.write(f"\ndados_extras:")
            if canal.dados_extras:
                self.stdout.write(f"   Keys: {list(canal.dados_extras.keys())}")
                
                if 'telegram_session' in canal.dados_extras:
                    session_string = canal.dados_extras['telegram_session']
                    self.stdout.write(f"   telegram_session: Presente ({len(session_string)} chars)")
                else:
                    self.stdout.write(self.style.ERROR("   telegram_session: Ausente"))
                
                if 'telegram_user' in canal.dados_extras:
                    telegram_user = canal.dados_extras['telegram_user']
                    self.stdout.write(f"   telegram_user: {telegram_user}")
                else:
                    self.stdout.write(self.style.WARNING("   telegram_user: Ausente"))
                
                if 'telegram_photo' in canal.dados_extras:
                    telegram_photo = canal.dados_extras['telegram_photo']
                    self.stdout.write(f"   telegram_photo: Presente ({len(telegram_photo) if telegram_photo else 0} chars)")
                else:
                    self.stdout.write(self.style.WARNING("   telegram_photo: Ausente"))
            else:
                self.stdout.write(self.style.ERROR("   dados_extras esta vazio!"))
            
            # Se não tem sessão, não pode sincronizar
            if not canal.dados_extras or 'telegram_session' not in canal.dados_extras:
                self.stdout.write(self.style.ERROR("\nErro: Sem telegram_session! O canal precisa ser autenticado primeiro."))
                self.stdout.write("\nPara autenticar:")
                self.stdout.write("1. Acesse o frontend")
                self.stdout.write("2. Adicione um novo canal Telegram")
                self.stdout.write("3. Insira o código de verificação recebido")
                return
            
            # Buscar dados do Telegram em tempo real
            self.stdout.write(f"\nBuscando dados do Telegram em tempo real...")
            
            loop = asyncio.get_event_loop()
            status_result = loop.run_until_complete(telegram_service.get_status(canal))
            
            if status_result.get('success') and status_result.get('connected'):
                user_data = status_result.get('user', {})
                self.stdout.write(self.style.SUCCESS("\nDados obtidos com sucesso!"))
                self.stdout.write(f"   Nome: {user_data.get('first_name')} {user_data.get('last_name') or ''}")
                self.stdout.write(f"   Username: @{user_data.get('username')}")
                self.stdout.write(f"   ID: {user_data.get('id')}")
                self.stdout.write(f"   Phone: {user_data.get('phone')}")
                
                # Atualizar dados_extras
                self.stdout.write(f"\nAtualizando dados_extras...")
                if not canal.dados_extras:
                    canal.dados_extras = {}
                
                canal.dados_extras['telegram_user'] = {
                    'id': user_data.get('id'),
                    'telegram_id': user_data.get('id'),
                    'username': user_data.get('username'),
                    'first_name': user_data.get('first_name'),
                    'last_name': user_data.get('last_name'),
                    'phone': user_data.get('phone'),
                    'name': user_data.get('first_name')
                }
                
                # Adicionar foto se disponível
                if status_result.get('profile_photo_url'):
                    canal.dados_extras['telegram_photo'] = status_result.get('profile_photo_url')
                    self.stdout.write(self.style.SUCCESS("   Foto de perfil adicionada"))
                
                # Salvar
                canal.save(update_fields=['dados_extras'])
                self.stdout.write(self.style.SUCCESS("\nCanal atualizado com sucesso!"))
                
                # Verificar
                canal.refresh_from_db()
                self.stdout.write(f"\nVerificacao pos-save:")
                self.stdout.write(f"   dados_extras tem {len(canal.dados_extras)} keys")
                self.stdout.write(f"   Keys: {list(canal.dados_extras.keys())}")
                
            else:
                self.stdout.write(self.style.ERROR(f"\nErro: {status_result.get('error') or status_result.get('message')}"))
                self.stdout.write("\nO canal pode estar desconectado ou a sessao invalida.")
                self.stdout.write("Tente autenticar novamente pelo frontend.")
                
        except Canal.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"\nErro: Canal {canal_id} nao encontrado!"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\nErro: {e}"))
            import traceback
            pass

