from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    TelegramIntegrationViewSet, EmailIntegrationViewSet,
    WhatsAppIntegrationViewSet, WebchatIntegrationViewSet,
    asaas_webhook,
    # evolution_webhook  # Desabilitado para evitar duplicação
)
from .meta_oauth import meta_callback
from .coexistence_webhooks import whatsapp_cloud_webhook

router = DefaultRouter()
router.register(r'telegram', TelegramIntegrationViewSet)
router.register(r'email', EmailIntegrationViewSet)
router.register(r'whatsapp', WhatsAppIntegrationViewSet)
router.register(r'webchat', WebchatIntegrationViewSet)

urlpatterns = [
    # ===================================================================
    # 🔵 Facebook OAuth Callback
    # IMPORTANTE: Esta rota será acessível em /api/auth/facebook/callback/
    # através do include em core/urls.py. URL configurada no painel da Meta:
    # https://api.niohub.com.br/api/auth/facebook/callback/
    # ===================================================================
    path('auth/facebook/callback/', meta_callback, name='facebook_callback'),
    
    
    # # Rota alternativa mantida para compatibilidade
    # path('meta/callback/', meta_callback, name='meta_callback'),
    
    # Rotas de integrações (depois do callback OAuth)
    path('integrations/', include(router.urls)),
    # ===================================================================
    # 🔵 WhatsApp Cloud API Webhook
    # IMPORTANTE: Esta rota deve estar registrada para receber eventos da Meta
    # URL: /api/webhook/whatsapp-cloud/
    # ===================================================================
    path('webhook/whatsapp-cloud/', whatsapp_cloud_webhook, name='whatsapp_cloud_webhook'),
    path('webhook/asaas/', asaas_webhook, name='asaas_webhook'),
    
    # path('webhook/evolution/', evolution_webhook, name='evolution_webhook'),  # Desabilitado para evitar duplicação
]
