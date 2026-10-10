from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .webhook_dispatcher import whatsapp_dispatcher, provider_channel_register, dispatcher_status
from .instagram_oauth import instagram_oauth_callback
from .asaas_webhook import asaas_webhook
from .inter_webhook import inter_webhook
from . import suggestions

router = DefaultRouter()
router.register(r'vps-servers', views.VpsServerViewSet, basename='vps-servers')
router.register(r'provedores', views.ProvedorViewSet, basename='provedores')
router.register(r'planos', views.PlanoViewSet, basename='planos')
router.register(r'canais', views.CanalViewSet, basename='canais')
router.register(r'companies', views.CompanyViewSet, basename='companies')
router.register(r'users', views.UserViewSet, basename='users')
router.register(r'audit-logs', views.AuditLogViewSet, basename='audit-logs')
router.register(r'mensagens-sistema', views.MensagemSistemaViewSet, basename='mensagens-sistema')
router.register(r'billing-templates', views.BillingTemplateViewSet, basename='billing-templates')
router.register(r'system-updates', views.SystemUpdateViewSet, basename='system-updates')
router.register(r'suggestions', suggestions.ProductSuggestionViewSet, basename='suggestions')

urlpatterns = [
    path('auth/login/', views.LoginView.as_view(), name='auth_login'),
    path('auth/niohub-panel/', views.NiohubPanelAccessView.as_view(), name='auth_niohub_panel'),
    path('auth/me/', views.UserMeView.as_view(), name='auth_me'),
    path('changelog/', views.changelog_view, name='changelog'),
    path('users/ping/', views.ping_view, name='users_ping'),
    path('users/status/', views.users_status_view, name='users_status'),
    path('health/', views.health_view, name='health'),
    path('system-config/', views.SystemConfigView.as_view(), name='system-config'),
    path('system-config/<int:pk>/', views.SystemConfigView.as_view(), name='system-config-detail'),
    path(
        'system-config/billing-whatsapp/embedded-signup-finish/',
        views.BillingWhatsAppEmbeddedSignupFinishView.as_view(),
        name='billing-whatsapp-embedded-signup-finish',
    ),
    path(
        'system-config/billing-whatsapp/test/',
        views.BillingWhatsAppTestView.as_view(),
        name='billing-whatsapp-test',
    ),
    path(
        'system-config/billing-whatsapp/templates/',
        views.BillingWhatsAppTemplatesView.as_view(),
        name='billing-whatsapp-templates',
    ),
    # ─── Webhook Central (Meta → Superadmin → Provedor) ───────────────────────
    path('webhook/whatsapp-cloud/', whatsapp_dispatcher, name='whatsapp_dispatcher'),
    path('webhook/whatsapp-cloud/status/', dispatcher_status, name='dispatcher_status'),
    path('auth/instagram/callback/', instagram_oauth_callback, name='instagram_oauth_callback'),
    # ─── Registro de Canal pelo Provedor ──────────────────────────────────────
    path('webhooks/provider/channel-register/', provider_channel_register, name='provider_channel_register'),
    path(
        'webhooks/provider/tenant-billing-status/',
        views.TenantBillingStatusView.as_view(),
        name='tenant_billing_status',
    ),
    path(
        'webhooks/provider/heartbeat/',
        views.ProviderHeartbeatView.as_view(),
        name='provider_heartbeat',
    ),
    path(
        'webhooks/provider/fx/usd-brl/',
        views.ProviderFxUsdBrlView.as_view(),
        name='provider_fx_usd_brl',
    ),
    path(
        'webhooks/provider/system-message-read/',
        views.SystemMessageReadReceiptView.as_view(),
        name='system_message_read',
    ),
    path(
        'webhooks/provider/suggestions/',
        suggestions.ProviderSuggestionsWebhookView.as_view(),
        name='provider_suggestions',
    ),
    path(
        'webhooks/provider/suggestions/<int:pk>/vote/',
        suggestions.ProviderSuggestionVoteWebhookView.as_view(),
        name='provider_suggestions_vote',
    ),
    path(
        'webhooks/provider/suggestions/<int:pk>/comments/',
        suggestions.ProviderSuggestionCommentsWebhookView.as_view(),
        name='provider_suggestions_comments',
    ),
    path('webhooks/asaas/', asaas_webhook, name='asaas_webhook'),
    path('webhooks/inter/', inter_webhook, name='inter_webhook'),
    # Aplicativo mobile do cliente (legado app_provedor → mesmo Postgres)
    path('mobile-app/', include('mobile_app.urls')),
    path('acs/', include('acs.urls')),
    path('', include(router.urls)),
]
