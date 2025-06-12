from django.urls import path
from . import views

urlpatterns = [
    path('api/get-model-info/', views.GetModelInfo.as_view(), name='get-model-info'),
    path('api/get-list/', views.GetList.as_view(), name='get-list'),
    path('api/create/', views.CreateRespondent.as_view(), name='create-respondent'),
    path('api/get/<int:pk>/', views.GetRespondentDetail.as_view(), name='get-respondent'),
    path('api/new-interaction/', views.NewInteraction.as_view(), name='new-interaction'),
]