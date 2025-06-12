from django.urls import path
from . import views

urlpatterns = [
    path('api/get-model-info/', views.GetModelInfo.as_view(), name='get-model-info'),
    path('api/get-list/', views.GetList.as_view(), name='get-list'),
    path('api/create/', views.CreateIndicator.as_view(), name='create-indicator'),
    path('api/get/<int:pk>/<int:resp>/', views.GetIndicator.as_view(), name='get-indicator'),
]