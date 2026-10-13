from django.urls import path

from marketing import views

urlpatterns = [
    path('threads/', views.threads, name='marketing-threads'),
    path('threads/<int:pk>/', views.thread_detail, name='marketing-thread-detail'),
    path('threads/<int:pk>/messages/', views.thread_messages, name='marketing-thread-messages'),
    path('threads/<int:pk>/actions/<int:action_id>/', views.thread_action, name='marketing-thread-action'),
    path('assets/upload/', views.upload_reference, name='marketing-asset-upload'),
    path('assets/<int:pk>/image/', views.asset_image, name='marketing-asset-image'),
    path('meta/', views.meta_connection, name='marketing-meta'),
    path('meta/connect/', views.meta_connect, name='marketing-meta-connect'),
    path('meta/options/', views.meta_options, name='marketing-meta-options'),
    path('meta/config/', views.meta_config, name='marketing-meta-config'),
    path('meta/campaigns/', views.meta_campaigns, name='marketing-meta-campaigns'),
    path('meta/campaigns/<str:campaign_id>/status/', views.meta_campaign_status, name='marketing-meta-campaign-status'),
]
