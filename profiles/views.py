from django.shortcuts import render
from users.restrictviewset import RoleRestrictedViewSet
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from profiles.models import FavoriteProject, FavoriteRespondent, FavoriteTask
from profiles.serializers import ProfileSerializer, FavoriteProjectSerializer, FavoriteRespondentSerializer, FavoriteTaskSerializer
from django.contrib.auth import get_user_model

User = get_user_model()



class ProfileViewSet(RoleRestrictedViewSet):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['organization', 'role', 'is_active']
    ordering_fields = ['last_name']
    search_fields = ['last_name','first_name', 'username'] 

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return User.objects.all()
        elif user.role in ['meofficer', 'manager']:
            return User.objects.filter(Q(organization=user.organization) | Q(organization__parent_organization=user.organization))
        return User.objects.filter(id=user.id)


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
