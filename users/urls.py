from django.urls import path, include
from .views import CookieTokenObtainPairView, CookieTokenRefreshView, ApplyForNewUser, MobileLoginView, current_user, logout_view, TestConnectionView, AdminResetPasswordView
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

urlpatterns = [
    path('request-token/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'), #get an access token
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token-refresh'), #get a refresh token
    path('mobile/request-token/', MobileLoginView.as_view(), name='mobile-login'), #get a mobile access token
    path('mobile-token/refresh/', TokenRefreshView.as_view(), name='mobile_token_refresh'), # get a mobile refresh token
    path('me/', current_user), #protected endpoint that returns a user's basic profile
    path('test-connection/', TestConnectionView.as_view(), name='test-connection'), #unprotected endpoint for checking connection
    path('logout/', logout_view), #logout
    path('create-user/', ApplyForNewUser.as_view(), name='create-user'), #creates a user
    path('admin-reset-password/', AdminResetPasswordView.as_view(), name='admin-reset-password'), #admin endpoint for resetting a password
    path('manage/', include('djoser.urls')), #djsoser helper urls for email password reset
]