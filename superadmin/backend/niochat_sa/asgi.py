import logging
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'niochat_sa.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import super_core.routing

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            super_core.routing.websocket_urlpatterns
        )
    ),
})

try:
    from niochat_sa.asgi_periodic import start_inline_periodic_tasks

    start_inline_periodic_tasks()
except Exception as periodic_err:
    logging.getLogger(__name__).warning(
        "[Superadmin ASGI periodic] não iniciado: %s", periodic_err, exc_info=True
    )
