"""
Comando Django para finalizar conversas em estado 'closing' que excederam a janela de tolerância.

Este comando deve ser executado periodicamente (ex: a cada 5 minutos) via cron ou agendador de tarefas.

Uso:
    python manage.py finalize_closing_conversations
    python manage.py finalize_closing_conversations --tolerance 2
"""
import logging
from django.core.management.base import BaseCommand
from conversations.closing_service import closing_service

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Finaliza conversas em estado "closing" que excederam a janela de tolerância'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tolerance',
            type=int,
            default=2,
            help='Período de tolerância em minutos (padrão: 2)',
        )

    def handle(self, *args, **options):
        tolerance = options['tolerance']
        
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(self.style.SUCCESS("FINALIZAÇÃO DE CONVERSAS EM 'CLOSING'"))
        self.stdout.write(self.style.SUCCESS("=" * 70))
        self.stdout.write(f"\nJanela de tolerância: {tolerance} minutos\n")
        
        try:
            stats = closing_service.process_final_closures(tolerance_minutes=tolerance)
            
            if stats['total_found'] == 0:
                self.stdout.write(self.style.SUCCESS("✓ Nenhuma conversa em 'closing' encontrada para finalizar."))
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ Processamento concluído:\n"
                        f"  • Total encontrado: {stats['total_found']}\n"
                        f"  • Finalizadas: {stats['finalized']}\n"
                        f"  • Erros: {stats['errors']}"
                    )
                )
            
            self.stdout.write(self.style.SUCCESS("\n" + "=" * 70))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Erro ao processar conversas: {e}"))
            logger.error(f"Erro ao finalizar conversas em 'closing': {e}", exc_info=True)
            raise

