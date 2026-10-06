from django.urls import path

from marketing import views

urlpatterns = [
    path('threads/', views.threads, name='marketing-threads'),
    path('threads/<int:pk>/', views.thread_detail, name='marketing-thread-detail'),
    path('threads/<int:pk>/messages/', views.thread_messages, name='marketing-thread-messages'),
    path('assets/', views.assets, name='marketing-assets'),
    path('assets/upload/', views.upload_reference, name='marketing-asset-upload'),
    path('assets/<int:pk>/', views.asset_detail, name='marketing-asset-detail'),
    path('assets/<int:pk>/image/', views.asset_image, name='marketing-asset-image'),
    path('settings/', views.engine_settings, name='marketing-settings'),
]
