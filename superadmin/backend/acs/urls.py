from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import public_api, views

router = DefaultRouter()
router.register(r'profiles', views.AcsProfileViewSet, basename='acs-profiles')
router.register(r'licenses', views.AcsLicenseViewSet, basename='acs-licenses')
router.register(r'hardware', views.AcsHardwareBindViewSet, basename='acs-hardware')
router.register(r'releases', views.AcsReleaseViewSet, basename='acs-releases')
router.register(r'deployment-logs', views.AcsDeploymentLogViewSet, basename='acs-deployment-logs')

urlpatterns = [
    path('', include(router.urls)),
]
