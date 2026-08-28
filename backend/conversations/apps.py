from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class ConversationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'conversations'
    
    def ready(self):
        """Importar signals e tarefas Dramatiq quando o app estiver pronto"""
        try:
            import conversations.signals
        except ImportError:
            pass
        
        # Iniciar o serviço de monitoramento de timeout nativo (back mesmo)
        try:
            from conversations.chatbot_timeout_service import chatbot_timeout_service
            chatbot_timeout_service.start()
        except Exception as e:
            logger.error(f"[ConversationsConfig] Falha ao iniciar ChatbotTimeoutService: {e}")
        
        # Importar tarefas Dramatiq para garantir que os atores sejam registrados
        # Isso é necessário para que o worker do Dramatiq encontre os atores
        try:
            import conversations.dramatiq_tasks  # noqa: F401
            # Verificar quantos atores foram registrados
            try:
                import dramatiq
                broker = dramatiq.get_broker()
                actors = list(broker.actors.keys())
                logger.info(f"[ConversationsConfig] Atores registrados após importar conversations.dramatiq_tasks: {len(actors)} atores - {actors}")
            except Exception as e:
                logger.debug(f"[ConversationsConfig] Não foi possível verificar atores: {e}")
        except ImportError as e:
            logger.warning(f"[ConversationsConfig] Erro ao importar conversations.dramatiq_tasks: {e}")