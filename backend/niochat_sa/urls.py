from django.contrib import admin
from django.urls import path, include

from acs import public_api as acs_public
from mobile_app import acs_views, public_api, push_views
from mobile_app.sgp_proxy import proxy_sgp_request
from super_core.views import operator_app_legal

urlpatterns = [
    path('admin/', admin.site.urls),
    # API pública do App Mobile (painelapp.gsfibra.com:8443/v1/...)
    path('v1/', include('mobile_app.v1_urls')),
    # Compatível com app Flutter legado (app_provedor): /api/sgp/... e /api/public/...
    path('api/sgp/<path:endpoint>', proxy_sgp_request, name='legacy-sgp-proxy'),
    path('api/public/config/', public_api.public_app_config, name='legacy-public-config'),
    path('api/public/warnings/', public_api.public_warnings, name='legacy-public-warnings'),
    path(
        'api/public/warnings/dismiss/',
        public_api.public_dismiss_warning,
        name='legacy-public-dismiss-warning',
    ),
    path('api/public/plans/', public_api.public_plans, name='legacy-public-plans'),
    path('api/public/server-time/', public_api.public_server_time, name='legacy-public-server-time'),
    path('api/public/operator-app/legal/', operator_app_legal, name='operator-app-legal'),
    path('api/app/register/', public_api.register_app_user, name='legacy-app-register'),
    path('api/devices/register/', push_views.register_device, name='legacy-devices-register'),
    path('api/wifi/config/', acs_views.wifi_config_api, name='legacy-wifi-config'),
    path('api/wifi/hosts/', acs_views.lan_hosts_api, name='legacy-wifi-hosts'),
    # ACS / GenieACS — mesmo contrato do painel_admin (VALIDACAO_URL)
    path('api/license/status', acs_public.license_status_api, name='acs_license_status'),
    path('api/license/status/', acs_public.license_status_api, name='acs_license_status_slash'),
    path('api/update/check', acs_public.update_check_api, name='acs_update_check'),
    path('api/update/check/', acs_public.update_check_api, name='acs_update_check_slash'),
    path('api/update/changelog', acs_public.changelog_api, name='acs_update_changelog'),
    path('api/update/changelog/', acs_public.changelog_api, name='acs_update_changelog_slash'),
    path('api/update/report', acs_public.update_report_api, name='acs_update_report'),
    path('api/update/report/', acs_public.update_report_api, name='acs_update_report_slash'),
    # API interna Superadmin / painel
    path('api/', include('super_core.urls')),
]
