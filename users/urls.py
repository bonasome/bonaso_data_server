from django.urls import path
from .views import CookieTokenObtainPairView, CookieTokenRefreshView, current_user, logout_view, ApplyForNewUser

from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

urlpatterns = [
    path('request-token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('me/', current_user),
    path('logout/', logout_view),
    path('create-user/', ApplyForNewUser.as_view(), name='create-user')
]