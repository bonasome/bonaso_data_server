from django.urls import path
from rest_framework.routers import DefaultRouter

from organizations.views import OrganizationViewSet

router = DefaultRouter()
router.register(r'', OrganizationViewSet, basename='organization')

urlpatterns = router.urls