from django.apps import AppConfig
import logging
import threading

logger = logging.getLogger(__name__)


class IntegrationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'integrations'
    
    def ready(self):
        """Importar tarefas Dramatiq quando o app estiver pronto"""
        # --- NOVA CHECAGEM ROBUSTA DE BANCO ---
        import sys
        from django.db import connection
        is_manage_cmd = any(arg in sys.argv for arg in ['migrate', 'makemigrations', 'collectstatic', 'check', 'shell', 'test'])
        if is_manage_cmd:
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM django_migrations LIMIT 1")
        except Exception:
            return
        # --------------------------------------

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

        self._schedule_voice_webhook_sync()

    def _schedule_voice_webhook_sync(self):
        """Após deploy, corrige webhooks Go→Django sem ação manual no painel."""
        from django.conf import settings

        if getattr(settings, 'ENVIRONMENT', '') != 'production':
            return

        def _run():
            import time

            time.sleep(5)
            try:
                from integrations.niohub_voice_calls import sync_all_voice_call_webhooks

                count = sync_all_voice_call_webhooks()
                if count:
                    logger.info('[IntegrationsConfig] voice webhooks sincronizados: %d', count)
            except Exception as exc:
                logger.warning('[IntegrationsConfig] sync voice webhooks: %s', exc)

        threading.Thread(
            target=_run,
            daemon=True,
            name='niohub-voice-webhook-sync',
        ).start()
