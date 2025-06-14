from django.urls import path
from rest_framework.routers import DefaultRouter

from indicators.views import IndicatorViewSet

router = DefaultRouter()
router.register(r'', IndicatorViewSet, basename='indicator')

urlpatterns = router.urls