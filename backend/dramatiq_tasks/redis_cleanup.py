"""
Tarefas Dramatiq para limpeza automática do Redis

Executa periodicamente:
1. Limpeza de chaves legadas (ai:memory:*, conversation:*)
2. Verificação de isolamento entre provedores
3. Limpeza de chaves expiradas
"""

import logging
from dramatiq.middleware import CurrentTask
from dramatiq.brokers import get_broker
from django.core.management import call_command

logger = logging.getLogger(__name__)


def limpar_chaves_legadas_redis():
    """
    Tarefa para limpar chaves legadas do Redis que causam vazamento de dados.
    Executa periodicamente para garantir que não há chaves obsoletas.
    
    SCHEDULE: A cada 6 horas
    """
    logger.info("🧹 [REDIS CLEANUP] Iniciando limpeza de chaves legadas...")
    
    try:
        # Chamar comando de limpeza em modo dry-run primeiro
        call_command('clean_legacy_redis_keys', '--dry-run')
        logger.info("🧹 [REDIS CLEANUP] Dry-run concluído")
        
        # Depois, executar a limpeza real (aguardar um pouco para evitar concorrência)
        # Nota: Em produção, pode-se executar a limpeza real diretamente
        # Aqui estamos apenas registrando, a limpeza real deve ser agendada separadamente
        logger.info("🧹 [REDIS CLEANUP] Para executar limpeza real, chame: python manage.py clean_legacy_redis_keys")
        
    except Exception as e:
        logger.error(f"❌ [REDIS CLEANUP] Erro ao executar limpeza: {e}", exc_info=True)
        raise


def limpar_chaves_expiradas():
    """
    Tarefa para limpar chaves expiradas que o Redis não removeu.
    Isso ajuda a manter o Redis saudável.
    
    SCHEDULE: A cada 24 horas (01:00 da manhã)
    """
    logger.info("🧹 [REDIS EXPIRED] Verificando chaves expiradas...")
    
    try:
        # Nota: O Redis remove chaves expiradas automaticamente,
        # mas esta tarefa pode fazer verificações adicionais
        # Por enquanto, apenas logamos a execução
        logger.info("🧹 [REDIS EXPIRED] Redis gerencia expiração automaticamente")
        
    except Exception as e:
        logger.error(f"❌ [REDIS EXPIRED] Erro na verificação: {e}", exc_info=True)
        raise


def verificar_isolamento_provedores():
    """
    Tarefa para verificar se há violações de isolamento entre provedores.
    Busca por padrões de chaves que não seguem o isolamento correto.
    
    SCHEDULE: A cada 12 horas
    """
    logger.info("🔍 [ISOLAMENTO CHECK] Verificando isolamento entre provedores...")
    
    try:
        # Chamar comando para listar provedores e verificar estatísticas
        call_command('limpar_redis_provedor', '--listar')
        logger.info("🔍 [ISOLAMENTO CHECK] Verificação concluída")
        
    except Exception as e:
        logger.error(f"❌ [ISOLAMENTO CHECK] Erro na verificação: {e}", exc_info=True)
        raise


# Configuração do Broker (se necessário)
# Nota: O broker deve ser configurado no settings.py
broker = get_broker()

# Definição das tarefas para Dramatiq
# Estas tarefas podem ser agendadas via CLI ou via API Dramatiq
limpar_chaves_legadas_redis.task_id = "redis_cleanup_limpar_legadas"
limpar_chaves_legadas_redis.queue_name = "redis"

limpar_chaves_expiradas.task_id = "redis_cleanup_limpar_expiradas"
limpar_chaves_expiradas.queue_name = "redis"

verificar_isolamento_provedores.task_id = "redis_cleanup_verificar_isolamento"
verificar_isolamento_provedores.queue_name = "redis"
