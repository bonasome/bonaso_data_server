from django.urls import path
from rest_framework.routers import DefaultRouter

from analysis.views import DashboardSettingViewSet, IndicatorChartSettingViewSet

router = DefaultRouter()
router.register(r'dashboards', DashboardSettingViewSet, basename='dashboard')
router.register(r'charts-indicator', IndicatorChartSettingViewSet, basename='indicator_chart')

urlpatterns = router.urls