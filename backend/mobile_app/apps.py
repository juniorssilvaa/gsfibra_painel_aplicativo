from django.apps import AppConfig


class MobileAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'mobile_app'
    verbose_name = 'Aplicativo Mobile do Provedor'

    def ready(self):
        from django.db.backends.signals import connection_created

        def _sqlite_pragma(sender, connection, **kwargs):
            if connection.vendor != 'sqlite':
                return
            cursor = connection.cursor()
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA busy_timeout=30000;')
            cursor.execute('PRAGMA synchronous=NORMAL;')

        connection_created.connect(_sqlite_pragma, dispatch_uid='mobile_app_sqlite_pragma')

