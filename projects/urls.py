from django.urls import path
from rest_framework.routers import DefaultRouter

from projects.views import ProjectViewSet, TaskViewSet, TargetViewSet, ClientViewSet, ProjectActivityViewSet

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'targets', TargetViewSet, basename='target')
router.register(r'clients', ClientViewSet, basename='client')

router.register(r'activities', ProjectActivityViewSet, basename='projectactivity')
urlpatterns = router.urls