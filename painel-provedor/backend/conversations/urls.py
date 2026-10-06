from django.urls import path, include, re_path
from rest_framework.routers import DefaultRouter
from .views import (
    ContactViewSet, InboxViewSet, ConversationViewSet,
    MessageViewSet, TeamViewSet, TeamMemberViewSet,
    serve_media_file, proxy_external_media, DashboardResponseTimeHourlyView, ConversationAnalysisView,
    TextCorrectionView, DashboardStatsView
)
from .views_internal_chat import (
    InternalChatRoomViewSet,
    InternalChatMessageViewSet,
    InternalChatParticipantViewSet,
    InternalChatUnreadCountView,
    InternalChatUnreadByUserView
)
from .views_private_chat import (
    PrivateMessageViewSet,
    PrivateUnreadCountsView,
    UsersListView,
    serve_private_chat_media,
)
from .views_csat import (
    CSATFeedbackViewSet,
    CSATRequestViewSet,
    process_csat_webhook
)
from integrations.voice_call_events_view import VoiceCallEventsView
from integrations.voice_call_incoming_lookup import VoiceCallIncomingLookupView
from integrations.voice_call_stream_url_view import VoiceCallStreamUrlView
from integrations.voice_call_webhook_view import VoiceCallWebhookView
from integrations.voice_calls_session_views import (
    VoiceCallSessionAcceptView,
    VoiceCallSessionHangupView,
    VoiceCallSessionRejectView,
    VoiceCallSessionWebRtcView,
)
from .recovery_views import (
    get_recovery_stats,
    analyze_conversations,
    send_recovery_campaign,
    get_recovery_settings,
    update_recovery_settings
)
from .ad_referral_views import ad_referrals_report
from .ai_learning_views import (
    ai_learning_export,
    ai_learning_item_detail,
    ai_learning_items,
    ai_learning_metrics,
)


router = DefaultRouter()
router.register(r'contacts', ContactViewSet, basename='contact')
router.register(r'inboxes', InboxViewSet)
router.register(r'conversations', ConversationViewSet)
router.register(r'messages', MessageViewSet)
router.register(r'teams', TeamViewSet)
router.register(r'team-members', TeamMemberViewSet)

# Chat interno
router.register(r'internal-chat/rooms', InternalChatRoomViewSet, basename='internal-chat-rooms')
router.register(r'internal-chat/messages', InternalChatMessageViewSet, basename='internal-chat-messages')
router.register(r'internal-chat/participants', InternalChatParticipantViewSet, basename='internal-chat-participants')

# Chat privado
router.register(r'private-messages', PrivateMessageViewSet, basename='private-messages')

# CSAT
router.register(r'csat/feedbacks', CSATFeedbackViewSet, basename='csat-feedbacks')
router.register(r'csat/requests', CSATRequestViewSet, basename='csat-requests')

urlpatterns = [
    path('text/correct/', TextCorrectionView.as_view(), name='text_correct'),
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('csat/feedbacks/stats/', CSATFeedbackViewSet.as_view({'get': 'stats'}), name='csat-feedback-stats'),
    path('conversations/dashboard_stats/', ConversationViewSet.as_view({'get': 'dashboard_stats'}), name='conversation-dashboard-stats'),
    path('voice-calls/events/', VoiceCallEventsView.as_view(), name='voice-calls-events'),
    path('voice-calls/stream-url/', VoiceCallStreamUrlView.as_view(), name='voice-calls-stream-url'),
    path('voice-calls/incoming-lookup/', VoiceCallIncomingLookupView.as_view(), name='voice-calls-incoming-lookup'),
    path('voice-calls/call-webhook/', VoiceCallWebhookView.as_view(), name='voice-calls-call-webhook'),
    path(
        'voice-calls/sessions/<str:session_id>/calls/<str:call_id>/webrtc/',
        VoiceCallSessionWebRtcView.as_view(),
        name='voice-calls-webrtc',
    ),
    path(
        'voice-calls/sessions/<str:session_id>/calls/<str:call_id>/accept/',
        VoiceCallSessionAcceptView.as_view(),
        name='voice-calls-accept',
    ),
    path(
        'voice-calls/sessions/<str:session_id>/calls/<str:call_id>/reject/',
        VoiceCallSessionRejectView.as_view(),
        name='voice-calls-reject',
    ),
    path(
        'voice-calls/sessions/<str:session_id>/calls/<str:call_id>/',
        VoiceCallSessionHangupView.as_view(),
        name='voice-calls-hangup',
    ),
    path('', include(router.urls)),
    # URLs específicas para recuperador de conversas (removidas - usando views separadas)
    # URL para servir arquivos de mídia
    # IMPORTANTE: Usar path converter em vez de str para capturar nomes de arquivo com espaços
    # A barra final é opcional
    re_path(r'^media/messages/(?P<conversation_id>\d+)/(?P<filename>[^/]+)/?$', serve_media_file, name='serve-media-file'),
    re_path(r'^media/private_chat/(?P<filename>[^/]+)/?$', serve_private_chat_media, name='serve-private-chat-media-api'),
    # URL para fazer proxy de mídia externa (evita CORS)
    path('media/proxy/', proxy_external_media, name='proxy-external-media'),

    
    # APIs específicas
    path('private-unread-counts/', PrivateUnreadCountsView.as_view(), name='private-unread-counts'),
    path('internal-chat-unread-count/', InternalChatUnreadCountView.as_view(), name='internal-chat-unread-count'),
    path('internal-chat-unread-by-user/', InternalChatUnreadByUserView.as_view(), name='internal-chat-unread-by-user'),
    path('users-list/', UsersListView.as_view(), name='users-list'),
    path('dashboard/response-time-hourly/', DashboardResponseTimeHourlyView.as_view(), name='dashboard-response-time-hourly'),
    path('analysis/', ConversationAnalysisView.as_view(), name='conversation-analysis'),
    path('test-analysis/', ConversationAnalysisView.as_view(), name='test-analysis'),
    
    # CSAT webhook
    path('csat/webhook/', process_csat_webhook, name='csat-webhook'),
    
    # Recuperação de conversas
    path('recovery/stats/', get_recovery_stats, name='recovery-stats'),
    path('recovery/analyze/', analyze_conversations, name='recovery-analyze'),
    path('recovery/campaign/', send_recovery_campaign, name='recovery-campaign'),
    path('recovery/settings/', get_recovery_settings, name='recovery-settings'),
    path('recovery/settings/update/', update_recovery_settings, name='recovery-settings-update'),
    path('ai-learning/metrics/', ai_learning_metrics, name='ai-learning-metrics'),
    path('ai-learning/items/', ai_learning_items, name='ai-learning-items'),
    path('ai-learning/items/<int:pk>/', ai_learning_item_detail, name='ai-learning-item-detail'),
    path('ai-learning/export/', ai_learning_export, name='ai-learning-export'),
    path('ad-referrals/report/', ad_referrals_report, name='ad-referrals-report'),

]

