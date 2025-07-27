from django.urls import path
from rest_framework.routers import DefaultRouter

from profiles.views import ProfileViewSet

router = DefaultRouter()
router.register(r'users', ProfileViewSet, basename='user')
urlpatterns = router.urls