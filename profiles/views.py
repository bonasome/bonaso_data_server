from django.shortcuts import render
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework.permissions import IsAuthenticated

from profiles.models import FavoriteProject, FavoriteRespondent, FavoriteTask
from profiles.serializers import FavoriteProjectSerializer, FavoriteRespondentSerializer, FavoriteTaskSerializer

class FavoriteTaskViewSet(RoleRestrictedViewSet):
    serializer_class = FavoriteTaskSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteTask.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class FavoriteProjectViewSet(RoleRestrictedViewSet):
    serializer_class = FavoriteProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteProject.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

class FavoriteRespondentViewSet(RoleRestrictedViewSet):
    serializer_class = FavoriteRespondentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteRespondent.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
