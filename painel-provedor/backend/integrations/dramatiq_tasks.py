"""
Tarefas Dramatiq para o módulo de integrações

Este módulo contém jobs periódicos e assíncronos relacionados a integrações,
especialmente renovação automática de tokens do WhatsApp Cloud API.

IMPORTANTE:
- Jobs devem ser idempotentes (pode rodar múltiplas vezes sem efeitos colaterais)
- Sempre tratar erros graciosamente (não quebrar o sistema)
- Logar adequadamente para observabilidade
"""

import dramatiq
import logging
import sys
import django
from django.conf import settings

# Configurar encoding UTF-8 para Windows
# Não substituir stdout/stderr durante "migrate" para evitar "I/O operation on closed file"
if sys.platform == 'win32' and 'migrate' not in sys.argv:
    import io
    try:
        if hasattr(sys.stderr, 'buffer'):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
        if hasattr(sys.stdout, 'buffer'):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except (ValueError, AttributeError, OSError):
        pass

# Configurar logging básico
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stderr
)

# Configurar Django antes de importar models
if not settings.configured:
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat.settings')
    django.setup()

from core.models import Canal
from .meta_token_service import check_and_renew_canal_token, token_needs_renewal
from .billing_reminder_service import run_billing_reminder_cycle
from datetime import datetime

logger = logging.getLogger(__name__)

# Tentar obter o broker atual
try:
    broker = dramatiq.get_broker()
    logger.info(f"Broker disponível: {type(broker).__name__}")
except Exception:
    logger.warning("Broker não configurado ainda - será configurado pelo dramatiq_config")


@dramatiq.actor(
    actor_name="renew_all_whatsapp_cloud_tokens",
    queue_name="niochat_integrations_queue",
    time_limit=300000  # 5 minutos - pode demorar se houver muitos canais
)
def renew_all_whatsapp_cloud_tokens():
    """
    Job diário que renova tokens do WhatsApp Cloud API próximos da expiração.
    
    POR QUE ESTE JOB EXISTE:
    - Tokens long-lived expiram em ~60 dias
    - Se expirarem, canais param de funcionar
    - Renovação automática evita interrupção do serviço
    
    POR QUE RODA DIARIAMENTE:
    - Verifica todos os canais uma vez por dia
    - Renova apenas os que precisam (≤ 7 dias para expirar)
    - Não sobrecarrega a API da Meta (rate limit)
    - Permite múltiplas tentativas se uma renovação falhar
    
    POR QUE NÃO RENOVA TODOS SEMPRE:
    - Rate limit da API da Meta
    - Tokens válidos não precisam ser renovados
    - Economia de recursos e chamadas de API
    
    FLUXO:
    1. Busca todos os canais WhatsApp Oficial ativos
    2. Para cada canal, verifica se precisa renovar
    3. Renova apenas os que expiram em ≤ 7 dias
    4. Loga sucesso/falha para cada canal
    5. Não desativa canais se renovação falhar (tenta novamente amanhã)
    
    AGENDAMENTO:
    - Deve ser agendado para rodar 1x por dia (ex: 02:00 AM)
    - Pode ser agendado via cron ou sistema de agendamento do Dramatiq
    
    Exemplo de agendamento (cron):
    0 2 * * * python manage.py shell -c "from integrations.dramatiq_tasks import renew_all_whatsapp_cloud_tokens; renew_all_whatsapp_cloud_tokens.send()"
    """
    logger.info("=" * 80)
    logger.info("Iniciando verificação de expiração de tokens WhatsApp Cloud API")
    logger.info("=" * 80)
    
    try:
        # Buscar todos os canais WhatsApp Oficial ativos
        canais = Canal.objects.filter(
            tipo="whatsapp_oficial",
            ativo=True
        ).select_related('provedor')
        
        total_canais = canais.count()
        logger.info(f"Encontrados {total_canais} canais WhatsApp Oficial ativos")
        
        if total_canais == 0:
            logger.info("Nenhum canal para verificar")
            return
        
        # Estatísticas
        renovados = 0
        nao_precisam = 0
        falhas = 0
        expirados = 0
        
        # Processar cada canal
        for canal in canais:
            try:
                # Extrair data de expiração para logging
                expires_at = None
                if canal.dados_extras and "token_expires_at" in canal.dados_extras:
                    try:
                        expires_at_str = canal.dados_extras["token_expires_at"]
                        expires_at = datetime.fromisoformat(expires_at_str)
                    except (ValueError, TypeError):
                        pass
                
                # Log do status do token
                if expires_at:
                    days_left = (expires_at - datetime.now()).days
                    if days_left > 0:
                        logger.info(f"Canal {canal.id} (provedor {canal.provedor_id}) - Token expira em {days_left} dias")
                    else:
                        logger.warning(f"Canal {canal.id} (provedor {canal.provedor_id}) - Token já expirou há {abs(days_left)} dias")
                        expirados += 1
                else:
                    logger.warning(f"Canal {canal.id} (provedor {canal.provedor_id}) - Sem data de expiração")
                
                # Verificar e renovar se necessário
                if check_and_renew_canal_token(canal):
                    renovados += 1
                elif token_needs_renewal(expires_at):
                    # Precisa renovar mas falhou
                    falhas += 1
                else:
                    # Não precisa renovar ainda
                    nao_precisam += 1
                    
            except Exception as e:
                logger.error(f"Erro ao processar canal {canal.id}: {str(e)}", exc_info=True)
                falhas += 1
        
        # Resumo final
        logger.info("=" * 80)
        logger.info("RESUMO DA RENOVAÇÃO DE TOKENS")
        logger.info(f"  Total de canais verificados: {total_canais}")
        logger.info(f"  Tokens renovados: {renovados}")
        logger.info(f"  Não precisam renovar ainda: {nao_precisam}")
        logger.info(f"  Falhas na renovação: {falhas}")
        logger.info(f"  Tokens expirados: {expirados}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Erro crítico no job de renovação de tokens: {str(e)}", exc_info=True)
        # Não re-raise - job deve falhar graciosamente
        # Tentará novamente no próximo ciclo


@dramatiq.actor(
    actor_name="send_superadmin_billing_reminders",
    queue_name="niochat_integrations_queue",
    time_limit=180000
)
def send_superadmin_billing_reminders():
    """
    Roda o ciclo de cobrança automática do canal exclusivo do superadmin.
    """
    try:
        result = run_billing_reminder_cycle()
        logger.info(f"[BillingReminder] Resultado do ciclo: {result}")
    except Exception as e:
        logger.error(f"[BillingReminder] Erro no ciclo de cobrança: {e}", exc_info=True)

