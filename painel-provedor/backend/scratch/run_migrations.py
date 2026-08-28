import os
import sys
import django
import io
from django.core.management import call_command

# Adiciona o diretório atual ao sys.path para encontrar o módulo niochat
sys.path.append(os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
django.setup()

# Tenta executar redirecionando stdout/stderr para buffers de memória
try:
    buf = io.StringIO()
    call_command('makemigrations', 'conversations', stdout=buf, stderr=buf)
    call_command('migrate', 'conversations', stdout=buf, stderr=buf)
    
    with open('migration_status.txt', 'w') as f:
        f.write("Sucesso\n")
        f.write(buf.getvalue())
except Exception as e:
    with open('migration_error.txt', 'w') as f:
        f.write(str(e))
