from django.urls import path
from rest_framework.routers import DefaultRouter

from analysis.views import DashboardSettingViewSet, TablesViewSet, LineListViewSet

router = DefaultRouter()
router.register(r'dashboards', DashboardSettingViewSet, basename='dashboard')
router.register(r'tables', TablesViewSet, basename='analysis')
router.register(r'lists', LineListViewSet, basename='linelist')
urlpatterns = router.urls