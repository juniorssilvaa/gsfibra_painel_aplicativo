#!/usr/bin/env python
"""
Script Python para ser executado pelo Cron.
Chama a task Dramatiq para finalizar conversas em 'closing'.

Uso no crontab:
*/2 * * * * /caminho/para/backend/scripts/finalize_closing_cron.py >> /var/log/niochat/finalize_closing.log 2>&1
"""
import os
import sys
import django

# Adicionar o diretório do backend ao path
script_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(script_dir)
sys.path.insert(0, backend_dir)

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
django.setup()

# Agora importar e executar
import dramatiq
from niochat.dramatiq_config import broker as configured_broker
from conversations.dramatiq_tasks import finalize_closing_conversations

def main():
    """Executa a task Dramatiq para finalizar conversas em 'closing'"""
    try:
        # Configurar broker
        current_broker = dramatiq.get_broker()
        if current_broker is not configured_broker:
            dramatiq.set_broker(configured_broker)
            finalize_closing_conversations.broker = configured_broker
        
        # Tentar enviar para a fila (assíncrono)
        try:
            message = finalize_closing_conversations.send()
            print(f"[CRON] Task Dramatiq agendada com sucesso: {message.message_id}")
            return 0
        except Exception as send_error:
            # Se falhar ao enviar, executar diretamente (síncrono)
            print(f"[CRON] Erro ao agendar task, executando diretamente: {send_error}")
            result = finalize_closing_conversations()
            print(f"[CRON] Executado diretamente: {result}")
            return 0
            
    except Exception as e:
        print(f"[CRON] Erro crítico: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())

