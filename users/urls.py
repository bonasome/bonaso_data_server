from django.urls import path
from .views import MyTokenObtainPairView, UserInfo
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)

urlpatterns = [
    path('api/request-token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('api/me/', UserInfo.as_view(), name='get-me'),
]