from django.urls import path
from rest_framework.routers import DefaultRouter

from social.views import SocialMediaPostViewSet

router = DefaultRouter()
router.register(r'posts', SocialMediaPostViewSet, basename='socialmediapost')
urlpatterns = router.urls