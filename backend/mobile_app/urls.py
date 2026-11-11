from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views, public_api, push_views, panel_api, support_views

router = DefaultRouter()
router.register(r'profiles', views.MobileAppProfileViewSet, basename='mobile-profiles')
router.register(r'app-users', views.MobileAppUserViewSet, basename='mobile-app-users')
router.register(r'warnings', views.MobileWarningViewSet, basename='mobile-warnings')
router.register(r'plans', views.MobilePlanViewSet, basename='mobile-plans')
router.register(
    r'notification-templates',
    views.MobileNotificationTemplateViewSet,
    basename='mobile-notification-templates',
)
router.register(
    r'scheduled-notifications',
    views.MobileScheduledNotificationViewSet,
    basename='mobile-scheduled-notifications',
)
router.register(
    r'notification-logs',
    views.MobileNotificationLogViewSet,
    basename='mobile-notification-logs',
)

urlpatterns = [
    # Admin Superadmin
    path('ai-config/', views.MobileAIConfigView.as_view(), name='mobile-ai-config'),

    # Panel / SGP (compatível com app_provedor /api/panel/integrations/sgp/)
    path('panel/integrations/sgp/', panel_api.get_sgp_integration, name='mobile-sgp-integration'),
    path(
        'panel/integrations/sgp/credentials/',
        panel_api.save_sgp_credentials,
        name='mobile-sgp-credentials',
    ),
    path(
        'panel/integrations/sgp/generate/',
        panel_api.generate_sgp_token,
        name='mobile-sgp-generate',
    ),
    path(
        'panel/integrations/sgp/webhook/',
        panel_api.update_webhook_url,
        name='mobile-sgp-webhook',
    ),
    path('panel/company/', panel_api.get_company, name='mobile-panel-company'),
    path('panel/users/', panel_api.panel_users, name='mobile-panel-users'),
    path('panel/users/<int:pk>/', panel_api.panel_user_detail, name='mobile-panel-user-detail'),

    # Público (app do cliente) — mesmos paths relativos do app_provedor sob /api/mobile-app/
    path('public/config/', public_api.public_app_config, name='mobile-public-config'),
    path('public/warnings/', public_api.public_warnings, name='mobile-public-warnings'),
    path(
        'public/warnings/dismiss/',
        public_api.public_dismiss_warning,
        name='mobile-public-dismiss-warning',
    ),
    path('public/plans/', public_api.public_plans, name='mobile-public-plans'),
    path('public/server-time/', public_api.public_server_time, name='mobile-public-server-time'),
    path('app/register/', public_api.register_app_user, name='mobile-app-register'),

    # Push
    path('devices/register/', push_views.register_device, name='mobile-devices-register'),
    path('webhooks/push/', push_views.push_webhook, name='mobile-push-webhook'),
    path('admin/push/send/', push_views.admin_send_push, name='mobile-admin-push-send'),
    path('verify-app-token/', support_views.verify_app_token, name='mobile-verify-app-token'),

    path('', include(router.urls)),
]
