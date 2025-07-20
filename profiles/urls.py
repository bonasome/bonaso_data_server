from django.urls import path
from rest_framework.routers import DefaultRouter

from profiles.views import ProfileViewSet, FavoriteProjectViewSet, FavoriteRespondentViewSet, FavoriteEventViewSet

router = DefaultRouter()
router.register(r'users', ProfileViewSet, basename='user')
router.register(r'favorite-respondents', FavoriteRespondentViewSet, basename='favoriterespondent')
router.register(r'favorite-events', FavoriteEventViewSet, basename='favoriteevent')
router.register(r'favorite-projects', FavoriteProjectViewSet, basename='favoriteproject')
urlpatterns = router.urls