from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Processa a fila de notificações push agendadas do app mobile.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Mantém o comando rodando em loop a cada 10 segundos.',
        )

    def handle(self, *args, **options):
        import time
        from django.utils import timezone
        from mobile_app.push_service import process_due_scheduled_notifications

        if options['loop']:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[{timezone.localtime().strftime('%H:%M:%S')}] "
                    'Iniciando processamento contínuo (loop 10s)...'
                )
            )
            while True:
                result = process_due_scheduled_notifications()
                self.stdout.write(
                    f"[{timezone.localtime().strftime('%H:%M:%S')}] "
                    f"processed={result.get('processed')} checked={result.get('checked')}"
                )
                time.sleep(10)
        else:
            result = process_due_scheduled_notifications()
            self.stdout.write(
                self.style.SUCCESS(
                    f"processed={result.get('processed')} checked={result.get('checked')}"
                )
            )
