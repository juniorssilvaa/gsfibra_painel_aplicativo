from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class IntegrationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations'
    
    def ready(self):
        """Importar tarefas Dramatiq quando o app estiver pronto"""
        # Importar tarefas Dramatiq para garantir que os atores sejam registrados
        # Isso é necessário para que o worker do Dramatiq encontre os atores
        try:
            import integrations.dramatiq_tasks  # noqa: F401
            # Verificar quantos atores foram registrados
            try:
                import dramatiq
                broker = dramatiq.get_broker()
                actors = list(broker.actors.keys())
                logger.info(f"[IntegrationsConfig] Atores registrados após importar integrations.dramatiq_tasks: {len(actors)} atores - {actors}")
            except Exception as e:
                logger.debug(f"[IntegrationsConfig] Não foi possível verificar atores: {e}")
        except ImportError as e:
            logger.warning(f"[IntegrationsConfig] Erro ao importar integrations.dramatiq_tasks: {e}")
