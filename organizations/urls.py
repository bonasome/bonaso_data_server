from django.urls import path
from . import views

urlpatterns = [
    path('api/get-list/', views.GetList.as_view(), name='get-list'),
]