from django.urls import path
from rest_framework.routers import DefaultRouter

from aggregates.views import AggregateViewSet

router = DefaultRouter()
router.register(r'', AggregateViewSet, basename='aggregate')

urlpatterns = router.urls