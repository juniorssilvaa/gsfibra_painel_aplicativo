from django.apps import AppConfig

class SuperCoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'super_core'

    def ready(self):
        import os
        # Evita rodar no processo principal do reload (só roda no worker)
        if os.environ.get('RUN_MAIN') == 'true':
            from .background_tasks import start_background_tasks
            start_background_tasks()
