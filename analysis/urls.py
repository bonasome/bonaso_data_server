from django.urls import path
from rest_framework.routers import DefaultRouter

from analysis.views import DashboardSettingViewSet, AnalysisViewSet

router = DefaultRouter()
router.register(r'dashboards', DashboardSettingViewSet, basename='dashboard')
router.register(r'counts', AnalysisViewSet, basename='analysis')

urlpatterns = router.urls