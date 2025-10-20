from django.urls import path
from rest_framework.routers import DefaultRouter

from indicators.views import IndicatorViewSet, AssessmentViewSet

router = DefaultRouter()
router.register(r'manage',IndicatorViewSet, basename='indicator')
router.register(r'assessments', AssessmentViewSet, basename='assessment')

urlpatterns = router.urls