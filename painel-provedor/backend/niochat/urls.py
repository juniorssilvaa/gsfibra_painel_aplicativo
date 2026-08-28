from django.contrib import admin
from django.urls import path, include, re_path, register_converter as django_register_converter
from conversations.views_private_chat import serve_private_chat_media
import django.urls

# Monkey-patch para evitar erro de registro duplicado do DRF
def safe_register_converter(converter, type_name):
    try:
        django_register_converter(converter, type_name)
    except ValueError:
        # Ignorar se já estiver registrado
        pass

# Aplicar o patch
django.urls.register_converter = safe_register_converter

def trigger_error(request):
    division_by_zero = 1 / 0

urlpatterns = [
    path('sentry-debug/', trigger_error),
    path('api/', include('core.urls')),
    re_path(
        r'^media/private_chat/(?P<filename>[^/]+)/?$',
        serve_private_chat_media,
        name='serve-private-chat-media',
    ),
]