"""
Comando para agendar a execução periódica da finalização de conversas em 'closing'.

Este comando pode ser usado para agendar a task Dramatiq para executar periodicamente.
"""
import logging
from django.core.management.base import BaseCommand
import dramatiq
from niochat.dramatiq_config import broker as configured_broker
from conversations.dramatiq_tasks import finalize_closing_conversations

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Agenda a task Dramatiq para finalizar conversas em "closing" periodicamente'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=120,  # 2 minutos em segundos
            help='Intervalo entre execuções em segundos (padrão: 120 = 2 minutos)',
        )
        parser.add_argument(
            '--once',
            action='store_true',
            help='Executar apenas uma vez (não agendar periodicamente)',
        )

    def handle(self, *args, **options):
        interval_seconds = options['interval']
        run_once = options['once']
        
        # Garantir que o broker correto está configurado
        current_broker = dramatiq.get_broker()
        if current_broker is not configured_broker:
            dramatiq.set_broker(configured_broker)
            finalize_closing_conversations.broker = configured_broker
        
        if run_once:
            # Executar apenas uma vez
            self.stdout.write(self.style.SUCCESS("Executando finalização de conversas em 'closing'..."))
            result = finalize_closing_conversations()
            self.stdout.write(self.style.SUCCESS(f"✓ Execução concluída: {result}"))
        else:
            # Agendar execução periódica
            self.stdout.write(
                self.style.SUCCESS(
                    f"Agendando execução periódica a cada {interval_seconds} segundos...\n"
                    "NOTA: Para execução periódica automática, use cron ou Task Scheduler."
                )
            )
            # Executar uma vez para demonstrar
            result = finalize_closing_conversations()
            self.stdout.write(self.style.SUCCESS(f"✓ Execução inicial concluída: {result}"))

