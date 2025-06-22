from django.urls import path
from .views import CookieTokenObtainPairView, CookieTokenRefreshView, ApplyForNewUser, MobileLoginView, current_user, logout_view, TestConnectionView
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

urlpatterns = [
    path('request-token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token-refresh'),
    path('mobile/request-token/', MobileLoginView.as_view(), name='mobile-login'),
    path('mobile-token/refresh/', TokenRefreshView.as_view(), name='mobile_token_refresh'),
    path('me/', current_user),
    path('test-connection/', TestConnectionView.as_view(), name='test-connection'),
    path('logout/', logout_view),
    path('create-user/', ApplyForNewUser.as_view(), name='create-user')
]