"""
API pública limpa do App Mobile — base: https://api.niohub.com.br/v1/

Exemplos:
  POST /v1/auth/login
  GET  /v1/home
  GET  /v1/plans
  GET  /v1/warnings
  POST /v1/warnings/dismiss
  GET  /v1/time
  POST /v1/devices/register
  GET  /v1/wifi/config
  GET  /v1/wifi/hosts
  POST /v1/webhooks/push
"""
from django.urls import path

from . import acs_views, public_api, push_views, support_views
from .sgp_proxy import proxy_sgp_request

urlpatterns = [
    # Proxy SGP (mesmo contrato do app legado /api/sgp/<endpoint>)
    path('sgp/<path:endpoint>', proxy_sgp_request, name='v1-sgp-proxy'),

    # ACS / GenieACS (Wi-Fi do modem) — mesmo contrato do app legado
    path('wifi/config', acs_views.wifi_config_api, name='v1-wifi-config'),
    path('wifi/config/', acs_views.wifi_config_api, name='v1-wifi-config-slash'),
    path('wifi/hosts', acs_views.lan_hosts_api, name='v1-wifi-hosts'),
    path('wifi/hosts/', acs_views.lan_hosts_api, name='v1-wifi-hosts-slash'),

    # Auth (login/registro do cliente no app)
    path('auth/login', public_api.register_app_user, name='v1-auth-login'),
    path('auth/login/', public_api.register_app_user, name='v1-auth-login-slash'),
    path('auth/register', public_api.register_app_user, name='v1-auth-register'),
    path('auth/register/', public_api.register_app_user, name='v1-auth-register-slash'),

    # Home / branding / ferramentas do provedor
    path('home', public_api.public_app_config, name='v1-home'),
    path('home/', public_api.public_app_config, name='v1-home-slash'),
    path(
        'branding/<int:provedor_id>/<str:kind>/',
        public_api.public_branding_file,
        name='v1-branding-file',
    ),

    # Planos
    path('plans', public_api.public_plans, name='v1-plans'),
    path('plans/', public_api.public_plans, name='v1-plans-slash'),

    # Avisos in-app
    path('warnings', public_api.public_warnings, name='v1-warnings'),
    path('warnings/', public_api.public_warnings, name='v1-warnings-slash'),
    path('warnings/dismiss', public_api.public_dismiss_warning, name='v1-warnings-dismiss'),
    path('warnings/dismiss/', public_api.public_dismiss_warning, name='v1-warnings-dismiss-slash'),

    # Relógio do servidor
    path('time', public_api.public_server_time, name='v1-time'),
    path('time/', public_api.public_server_time, name='v1-time-slash'),

    # Push / devices
    path('devices/register', push_views.register_device, name='v1-devices-register'),
    path('devices/register/', push_views.register_device, name='v1-devices-register-slash'),
    path('webhooks/push', push_views.push_webhook, name='v1-webhooks-push'),
    path('webhooks/push/', push_views.push_webhook, name='v1-webhooks-push-slash'),

    # Chat de atendimento no app (canal do painel)
    path('support/messages', support_views.support_messages, name='v1-support-messages'),
    path('support/messages/', support_views.support_messages, name='v1-support-messages-slash'),
    path('support/reactions', support_views.support_reactions, name='v1-support-reactions'),
    path('support/reactions/', support_views.support_reactions, name='v1-support-reactions-slash'),
    path('support/outbound', support_views.support_outbound, name='v1-support-outbound'),
    path('support/outbound/', support_views.support_outbound, name='v1-support-outbound-slash'),
    path('support/files/<uuid:media_id>', support_views.support_media_file, name='v1-support-file'),
    path('support/files/<uuid:media_id>/', support_views.support_media_file, name='v1-support-file-slash'),
]
