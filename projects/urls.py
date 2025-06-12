from django.urls import path
from . import views

urlpatterns = [
    path('api/get-list/', views.GetList.as_view(), name='get-list'),
    path('api/create/', views.CreateProject.as_view(), name='create-project'),
    path('api/get-model-info/', views.GetModelInfo.as_view(), name='get-model-info'),
    path('api/<int:pk>/get-indicators/', views.GetProjectIndicators.as_view(), name='get-indicators'),
    path('api/add-indicator/', views.AddProjectIndicator.as_view(), name='add-indicator'),
    path('api/<int:pk>/get-orgs/', views.GetProjectOrgs.as_view(), name='get-orgs'),
    path('api/add-org/', views.AddProjectOrg.as_view(), name='add-org'),
    path('api/<int:pk>/get-tasks/', views.GetProjectTasks.as_view(), name='get-task'),
    path('api/add-task/', views.AddTask.as_view(), name='add-task'),
    path('api/my-tasks', views.MyTasks.as_view(), name='my-tasks'),
]