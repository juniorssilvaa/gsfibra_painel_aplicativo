from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt
from rest_framework.routers import DefaultRouter
from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes
from . import views
from . import totp_views
from . import app_legal_views
from conversations import app_mobile
from integrations.instagram_oauth import instagram_oauth_finish_internal
from .views_provider_config import ProviderConfigView
from .sgp_views import SGPIntegrationViewSet
from .asaas_support_views import AsaasSupportViewSet
from .acs_views import ACSIntegrationViewSet

# Router apenas com viewsets existentes em core.views
router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='users')
router.register(r'canais', views.CanalViewSet, basename='canais')
router.register(r'audit-logs', views.AuditLogViewSet, basename='audit-logs')
router.register(r'provedores', views.ProvedorViewSet, basename='provedores')
router.register(r'companies', views.CompanyViewSet, basename='companies')
router.register(r'mensagens-sistema', views.MensagemSistemaViewSet, basename='mensagens-sistema')
router.register(r'integrations/telegram', views.TelegramIntegrationViewSet, basename='telegram-integrations')
router.register(r'integrations/email', views.EmailIntegrationViewSet, basename='email-integrations')
router.register(r'integrations/whatsapp', views.WhatsAppIntegrationViewSet, basename='whatsapp-integrations')
router.register(r'integrations/webchat', views.WebchatIntegrationViewSet, basename='webchat-integrations')
router.register(r'chatbot-flows', views.ChatbotFlowViewSet, basename='chatbot-flows')
router.register(r'planos', views.PlanoViewSet, basename='planos')
router.register(r'respostas-rapidas', views.RespostaRapidaViewSet, basename='respostas-rapidas')
router.register(r'provider-gallery', views.ProviderGalleryImageViewSet, basename='provider-gallery')
router.register(r'reminders', views.UserReminderViewSet, basename='reminders')
router.register(r'suggestions', views.ProviderSuggestionViewSet, basename='suggestions')
router.register(r'sgp', SGPIntegrationViewSet, basename='sgp')
router.register(r'asaas-support', AsaasSupportViewSet, basename='asaas-support')
router.register(r'acs', ACSIntegrationViewSet, basename='acs')

urlpatterns = [
    # Rotas específicas ANTES do router para evitar conflitos
    path('webhooks/admin/provider-status/', csrf_exempt(views.AdminProviderStatusWebhookView.as_view()), name='webhook-admin-provider-status'),
    path('webhooks/admin/sync-niohub/', csrf_exempt(views.AdminSyncNiohubWebhookView.as_view()), name='webhook-admin-sync-niohub'),
    path('webhooks/admin/upsert-user/', csrf_exempt(views.AdminUpsertUserWebhookView.as_view()), name='webhook-admin-upsert-user'),
    path('webhooks/admin/delete-user/', csrf_exempt(views.AdminDeleteUserWebhookView.as_view()), name='webhook-admin-delete-user'),
    path('webhooks/admin/users-status/', csrf_exempt(views.AdminUsersStatusWebhookView.as_view()), name='webhook-admin-users-status'),
    path('webhooks/admin/maintenance/', csrf_exempt(views.AdminMaintenanceWebhookView.as_view()), name='webhook-admin-maintenance'),
    path('webhooks/admin/system-message/', csrf_exempt(views.AdminSystemMessageWebhookView.as_view()), name='webhook-admin-system-message'),
    path('webhooks/inbound/', csrf_exempt(views.InboundWebhookView.as_view()), name='webhook-inbound'),
    path(
        'webhooks/app-mobile/',
        csrf_exempt(app_mobile.AppMobileInboundWebhookView.as_view()),
        name='webhook-app-mobile',
    ),
    path(
        'webhooks/app-mobile/messages/',
        csrf_exempt(app_mobile.AppMobileMessagesWebhookView.as_view()),
        name='webhook-app-mobile-messages',
    ),
    path(
        'webhooks/internal/instagram-oauth-finish/',
        csrf_exempt(instagram_oauth_finish_internal),
        name='webhook-instagram-oauth-finish',
    ),
    path('auth/login/', csrf_exempt(permission_classes([AllowAny])(views.LoginView.as_view())), name='auth_login'),
    path('auth/2fa/verify-login/', csrf_exempt(permission_classes([AllowAny])(totp_views.TwoFactorVerifyLoginView.as_view())), name='auth_2fa_verify_login'),
    path('auth/2fa/', totp_views.TwoFactorSetupView.as_view(), name='auth_2fa_setup'),
    path('auth/2fa/recreate/', totp_views.TwoFactorRecreateView.as_view(), name='auth_2fa_recreate'),
    path('auth/2fa/enable/', totp_views.TwoFactorEnableView.as_view(), name='auth_2fa_enable'),
    path('auth/2fa/disable/', totp_views.TwoFactorDisableView.as_view(), name='auth_2fa_disable'),
    path('auth/logout/', views.LogoutView.as_view(), name='auth_logout'),
    path('auth/refresh/', views.RefreshTokenView.as_view(), name='auth_refresh'),
    path('auth/realtime-ticket/', views.RealtimeTicketView.as_view(), name='auth_realtime_ticket'),
    path('auth/media-sign/', views.MediaSignView.as_view(), name='auth_media_sign'),
    path('auth/me/', views.UserMeView.as_view(), name='auth_me'),
    path('users/ping/', views.UsersPingView.as_view(), name='users_ping'),
    path('app/legal/', app_legal_views.operator_app_legal, name='operator_app_legal'),
    path('users/status/', views.UserViewSet.as_view({'get': 'status'}), name='users_status'),
    path('health/', views.health_view, name='health'),
    path('health', views.health_view, name='health_no_slash'),  # Sem trailing slash também funciona
    path('tenant-context/', views.tenant_context_view, name='tenant-context'),
    path('sentry-test/', views.sentry_test_view, name='sentry-test'),
    path('changelog/', views.changelog_view, name='changelog'),
    path('supabase-config/', views.supabase_config_view, name='supabase-config'),
    path('system-config/', views.SystemConfigView.as_view(), name='system-config'),
    path('system-config/<int:pk>/', views.SystemConfigView.as_view(), name='system-config-detail'),
    path('system-config/billing-whatsapp/embedded-signup-finish/', views.BillingWhatsAppEmbeddedSignupFinishView.as_view(), name='billing-whatsapp-embedded-signup-finish'),
    path('system-config/billing-whatsapp/templates/', views.BillingWhatsAppTemplatesView.as_view(), name='billing-whatsapp-templates'),
    path('system-config/billing-whatsapp/templates/<path:template_id>/', views.BillingWhatsAppTemplateDeleteView.as_view(), name='billing-whatsapp-template-delete'),
    path('provider/config/', ProviderConfigView.as_view(), name='provider-config'),
    path('media/provider-gallery/<int:image_id>/', views.serve_provider_gallery_media, name='provider-gallery-media'),

    # Router com viewsets (deve vir depois das rotas específicas)
    path('', include(router.urls)),
    
    # Incluir URLs de outros apps
    path('', include('conversations.urls')),
    path('', include('integrations.urls')),
    path('marketing/', include('marketing.urls')),
    path('campanhas/', include('campaigns.urls')),
    
    # Incluir URLs do WhatsApp (UazAPI)
    path('whatsapp/', include('core.whatsapp_urls')),

    # Rotas de Super Admin - Gestão de Contatos
    path('super-admin/contacts/', views.super_admin_contacts, name='super_admin_contacts'),
    path('super-admin/contacts/<int:pk>/delete/', views.super_admin_contact_delete, name='super_admin_contact_delete'),
]
