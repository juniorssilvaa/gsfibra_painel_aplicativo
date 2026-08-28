"""
Management command para renovar tokens do WhatsApp Cloud API

Este comando pode ser executado manualmente ou agendado via cron.

Uso:
    python manage.py renew_whatsapp_tokens

Agendamento (cron - rodar 1x por dia às 02:00):
    0 2 * * * cd /path/to/project && /path/to/venv/bin/python manage.py renew_whatsapp_tokens

Ou via Dramatiq (recomendado):
    from integrations.dramatiq_tasks import renew_all_whatsapp_cloud_tokens
    renew_all_whatsapp_cloud_tokens.send()
"""

from django.core.management.base import BaseCommand
from integrations.dramatiq_tasks import renew_all_whatsapp_cloud_tokens


class Command(BaseCommand):
    help = 'Renova tokens do WhatsApp Cloud API que estão próximos da expiração'

    def handle(self, *args, **options):
        """
        Executa a renovação de tokens.
        
        Pode ser chamado:
        - Manualmente via manage.py
        - Via cron (agendamento)
        - Via Dramatiq (recomendado para produção)
        """
        self.stdout.write('Iniciando renovação de tokens WhatsApp Cloud API...')
        
        try:
            # Chamar a função diretamente (não via Dramatiq para execução imediata)
            # Em produção, use: renew_all_whatsapp_cloud_tokens.send()
            renew_all_whatsapp_cloud_tokens()
            
            self.stdout.write(
                self.style.SUCCESS('✓ Renovação de tokens concluída com sucesso')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'✗ Erro ao renovar tokens: {str(e)}')
            )
            raise

