from django.urls import path
from rest_framework.routers import DefaultRouter

from messaging.views import AnnouncementViewSet, MessageViewSet, AlertViewSet

router = DefaultRouter()
router.register(r'announcements', AnnouncementViewSet, basename='announcement')
router.register(r'dm', MessageViewSet, basename='dm')
router.register(r'alerts', AlertViewSet, basename='alert')

urlpatterns = router.urls