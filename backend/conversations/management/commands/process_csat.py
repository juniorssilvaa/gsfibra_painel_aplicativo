from django.core.management.base import BaseCommand
from django.utils import timezone
from conversations.models import CSATRequest
from conversations.csat_automation import CSATAutomationService
import pytz

class Command(BaseCommand):
    help = 'Processa CSAT requests pendentes que já deveriam ter sido enviados'

    def handle(self, *args, **options):
        belem_tz = pytz.timezone('America/Belem')
        now = timezone.now().astimezone(belem_tz)
        
        self.stdout.write(f'Verificando CSATs pendentes às {now}')
        
        # Buscar CSATs pendentes que já deveriam ter sido enviados
        pending_csats = CSATRequest.objects.filter(status='pending')
        
        processed = 0
        for csat_request in pending_csats:
            if csat_request.scheduled_send_at:
                scheduled_local = csat_request.scheduled_send_at.astimezone(belem_tz)
                if now > scheduled_local:
                    self.stdout.write(f'Processando CSAT {csat_request.id} (agendado para {scheduled_local})')
                    try:
                        # Tentar enviar via Dramatiq primeiro (se ainda não foi enviado)
                        from conversations.tasks import send_csat_message
                        try:
                            # Enviar para fila default
                            message = send_csat_message.send(csat_request.id)
                            self.stdout.write(f'[INFO] Tarefa enviada para Dramatiq (fila default). Message ID: {message.message_id if hasattr(message, "message_id") else "N/A"}')
                            # Aguardar um pouco para ver se foi processada
                            import time
                            time.sleep(2)
                            csat_request.refresh_from_db()
                            if csat_request.status == 'sent':
                                self.stdout.write(self.style.SUCCESS(f'[OK] CSAT {csat_request.id} enviado com sucesso via Dramatiq'))
                                processed += 1
                                continue
                        except Exception as dramatiq_error:
                            self.stdout.write(f'[INFO] Erro ao enviar via Dramatiq: {dramatiq_error}, tentando metodo direto...')
                        
                        # Fallback: usar método direto se Dramatiq falhar
                        result = CSATAutomationService.send_csat_message(csat_request.id)
                        if result:
                            self.stdout.write(self.style.SUCCESS(f'[OK] CSAT {csat_request.id} enviado com sucesso (metodo direto)'))
                            processed += 1
                        else:
                            self.stdout.write(self.style.ERROR(f'[ERRO] Falha ao enviar CSAT {csat_request.id}'))
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f'[ERRO] Erro ao processar CSAT {csat_request.id}: {e}'))
                else:
                    self.stdout.write(f'[INFO] CSAT {csat_request.id} ainda nao e hora (agendado para {scheduled_local})')
        
        self.stdout.write(self.style.SUCCESS(f'Processados {processed} CSATs'))

