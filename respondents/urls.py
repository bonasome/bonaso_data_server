from django.urls import path
from rest_framework.routers import DefaultRouter

from respondents.views.respondent_viewset import RespondentViewSet
from respondents.views.interaction_viewset import InteractionViewSet


router = DefaultRouter()
router.register(r'respondents', RespondentViewSet, basename='respondent')
router.register(r'interactions', InteractionViewSet, basename='interaction')
urlpatterns = router.urls
