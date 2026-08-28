from django.urls import re_path
from .consumers import (
    ConversationConsumer,
    NotificationConsumer,
    DashboardConsumer,
    PainelConsumer,
    UserStatusConsumer,
)
from .consumers_internal_chat import (
    InternalChatConsumer,
    InternalChatNotificationConsumer,
)
from .consumers_private_chat import PrivateChatConsumer

websocket_urlpatterns = [
    # Conversas
    re_path(r"^ws/conversations/(?P<conversation_id>\w+)/?$", ConversationConsumer.as_asgi()),

    # Notificações (com ou sem user_id)
    re_path(r"^ws/notifications/(?P<user_id>\w+)/?$", NotificationConsumer.as_asgi()),
    re_path(r"^ws/notifications/?$", NotificationConsumer.as_asgi()),

    # Dashboard
    re_path(r"^ws/conversas_dashboard/?$", DashboardConsumer.as_asgi()),

    # Painel por provedor
    re_path(r"^ws/painel/(?P<provedor_id>\w+)/?$", PainelConsumer.as_asgi()),
    re_path(r"^ws/painel/?$", PainelConsumer.as_asgi()),

    # Status do usuário (com ou sem user_id)
    re_path(r"^ws/user/(?P<user_id>\w+)/?$", UserStatusConsumer.as_asgi()),
    re_path(r"^ws/user_status/?$", UserStatusConsumer.as_asgi()),

    # Chat interno
    re_path(r"^ws/internal-chat/notifications/?$", InternalChatNotificationConsumer.as_asgi()),
    re_path(r"^ws/internal-chat/(?P<room_id>\w+)/?$", InternalChatConsumer.as_asgi()),

    # Chat privado
    re_path(r"^ws/private-chat/?$", PrivateChatConsumer.as_asgi()),
]