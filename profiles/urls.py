from django.urls import path
from rest_framework.routers import DefaultRouter

from profiles.views import FavoriteProjectViewSet, FavoriteRespondentViewSet, FavoriteTaskViewSet

router = DefaultRouter()
router.register(r'favorite-respondents', FavoriteRespondentViewSet, basename='favoriterespondent')
router.register(r'favorite-tasks', FavoriteTaskViewSet, basename='favoritetask')
router.register(r'favorite-projects', FavoriteProjectViewSet, basename='favoriteproject')
urlpatterns = router.urls