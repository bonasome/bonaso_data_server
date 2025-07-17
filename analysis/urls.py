from django.urls import path
from rest_framework.routers import DefaultRouter

from analysis.views import AnalysisViewSet

router = DefaultRouter()
router.register(r'', AnalysisViewSet, basename='analysis')

urlpatterns = router.urls