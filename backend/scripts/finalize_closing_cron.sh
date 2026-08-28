#!/bin/bash
# Script para ser executado pelo Cron
# Chama a task Dramatiq para finalizar conversas em 'closing'

# Configurar variáveis (ajuste conforme necessário)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="${BACKEND_DIR}/venv/bin/python"

# Se estiver usando Docker, ajuste o caminho
# VENV_PYTHON="python"  # Para Docker

# Mudar para o diretório do backend
cd "$BACKEND_DIR" || exit 1

# Executar a task Dramatiq via comando Django
"$VENV_PYTHON" manage.py shell << EOF
import dramatiq
from niochat.dramatiq_config import broker as configured_broker
from conversations.dramatiq_tasks import finalize_closing_conversations

# Configurar broker
dramatiq.set_broker(configured_broker)
finalize_closing_conversations.broker = configured_broker

# Executar a task
try:
    result = finalize_closing_conversations.send()
    print(f"Task agendada com sucesso: {result}")
except Exception as e:
    print(f"Erro ao agendar task: {e}")
    # Se falhar, executar diretamente (síncrono)
    try:
        result = finalize_closing_conversations()
        print(f"Executado diretamente: {result}")
    except Exception as e2:
        print(f"Erro ao executar diretamente: {e2}")
EOF

exit $?

