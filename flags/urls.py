from django.urls import path
from rest_framework.routers import DefaultRouter

from flags.views import FlagViewSet

router = DefaultRouter()
router.register(r'', FlagViewSet, basename='flag')
urlpatterns = router.urls