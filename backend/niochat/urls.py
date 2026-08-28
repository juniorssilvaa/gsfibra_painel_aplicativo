from django.contrib import admin
from django.urls import path, include, register_converter as django_register_converter
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
]