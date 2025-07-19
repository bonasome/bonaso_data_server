from django.urls import path
from rest_framework.routers import DefaultRouter

from messaging.views import AnnouncementViewSet, MessageViewSet

router = DefaultRouter()
router.register(r'announcements', AnnouncementViewSet, basename='announcement')
router.register(r'dm', MessageViewSet, basename='dm')

urlpatterns = router.urls