from django.urls import path
from rest_framework.routers import DefaultRouter

from uploads.views import NarrativeReportViewSet

router = DefaultRouter()
router.register(r'narrative-report', NarrativeReportViewSet, basename='narrativereport')

urlpatterns = router.urls