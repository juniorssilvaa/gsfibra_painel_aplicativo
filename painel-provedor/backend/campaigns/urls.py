from django.urls import path

from campaigns import views

urlpatterns = [
    path('', views.campaigns),
    path('canais/', views.channels),
    path('templates/', views.templates),
    path('<int:pk>/', views.campaign_detail),
    path('<int:pk>/destinatarios/', views.recipients),
    path('<int:pk>/destinatarios/csv/', views.recipients_csv),
    path('<int:pk>/cabecalho/', views.header_file),
    path('<int:pk>/disparar/', views.dispatch),
    path('<int:pk>/cancelar/', views.cancel),
]
