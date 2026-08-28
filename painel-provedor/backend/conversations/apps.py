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
        
        # --- NOVA CHECAGEM ROBUSTA DE BANCO ---
        import sys
        from django.db import connection
        
        # 1. Ignorar comandos óbvios de sistema
        is_manage_cmd = any(arg in sys.argv for arg in ['migrate', 'makemigrations', 'collectstatic', 'check', 'shell', 'test'])
        if is_manage_cmd:
            return

        # 2. Verificar se o banco de dados está pronto e as tabelas básicas existem
        try:
            with connection.cursor() as cursor:
                # Se esta query falhar, o banco não está pronto ou a tabela de migrações não existe
                cursor.execute("SELECT 1 FROM django_migrations LIMIT 1")
        except Exception:
            logger.info("[ConversationsConfig] Banco de dados não inicializado ou migrações pendentes. Pulando serviços de background.")
            return
        # --------------------------------------

        # Iniciar thread de timeout do chatbot (varredura a cada ~60s).
        # Opcionalmente desliga-se com CHATBOT_TIMEOUT_DISABLE_BACKGROUND_THREAD=1 para evitar
        # corrida duplicada com niochat.asgi_periodic (recomendado em dev com SQLite + Daphne).
        try:
            import os
            from conversations.chatbot_timeout_service import chatbot_timeout_service

            disable_bg = os.environ.get("CHATBOT_TIMEOUT_DISABLE_BACKGROUND_THREAD", "").lower() in (
                "1",
                "true",
                "yes",
            )
            if not disable_bg:
                chatbot_timeout_service.start()
            else:
                logger.info(
                    "[ConversationsConfig] ChatbotTimeoutService (thread): desativado por env; "
                    "varreduras vêm só do ASGI periodic / outro scheduler."
                )
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