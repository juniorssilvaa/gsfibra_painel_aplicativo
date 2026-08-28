"""
Inicialização do pacote niochat.

Responsabilidade DESTE arquivo:
- Garantir que a configuração do Dramatiq seja carregada
  assim que o Django iniciar.
- NÃO inicializar o Django manualmente.
- NÃO criar broker aqui.
- NÃO importar tarefas diretamente.

O broker é configurado em:
    niochat.dramatiq_config

E o registro das tasks ocorre nos AppConfig.ready()
de cada app (ex: conversations.apps.ConversationsConfig).
"""

# ============================================
# PATCH CRÍTICO: Corrigir supports_color ANTES de qualquer coisa
# ============================================
# Isso deve ser feito antes de importar Django para evitar erro quando stdout está fechado
import sys

def safe_supports_color():
    """Versão segura de supports_color que não falha quando stdout está fechado"""
    try:
        if not hasattr(sys.stdout, 'isatty'):
            return False
        try:
            return sys.stdout.isatty()
        except (ValueError, AttributeError, OSError):
            return False
    except Exception:
        return False

# Aplicar patch ANTES de importar Django
try:
    import django.core.management.color
    django.core.management.color.supports_color = safe_supports_color
except (ImportError, AttributeError):
    # Se Django ainda não foi importado, será aplicado depois
    pass

# Importar o módulo inteiro é INTENCIONAL
# Isso garante que:
# - dramatiq_config.py seja executado
# - dramatiq.set_broker(...) seja chamado
# - NÃO exista fallback para localhost:5672
import niochat.dramatiq_config  # noqa: F401
