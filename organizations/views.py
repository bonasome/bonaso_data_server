from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from django.db.models import Case, When, Value, IntegerField
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics
from rest_framework.decorators import action
from rest_framework import status
from django.db.models import Q
from users.restrictviewset import RoleRestrictedViewSet
from organizations.models import Organization
from projects.models import Project, Task
from organizations.serializers import OrganizationListSerializer, OrganizationSerializer
from django.contrib.auth import get_user_model
User = get_user_model()

class OrganizationViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Organization.objects.none()
    serializer_class = OrganizationSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    filterset_fields = ['project', 'parent_organization', 'indicator']
    ordering_fields = ['name']
    search_fields = ['name'] 
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)
        if role == 'admin':
            queryset = Organization.objects.all()
        elif role and org:
            queryset =  Organization.objects.filter(Q(parent_organization=org) | Q(id=org.id))
        else:
            return Organization.objects.none()
        parent_organization = self.request.query_params.get('parent_organization')
        if parent_organization:
            queryset = queryset.filter(Q(parent_organization__id=parent_organization) | Q(id=parent_organization)).annotate(priority=Case(
                   When(pk=parent_organization, then=Value(0)),
                   default=Value(1),
                   output_field=IntegerField(),
               )
           ).order_by('priority', 'name')
            
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(projectorganization__project__id=project_id)
            
        indicator_id = self.request.query_params.get('indicator')
        if indicator_id:
            tasks = Task.objects.filter(organization__in=queryset, indicator__id=indicator_id)
            queryset = queryset.filter(id__in=tasks.values_list('organization_id', flat=True))
        return queryset
        


    def get_serializer_class(self):
        if self.action == 'list':
            return OrganizationListSerializer
        else:
            return OrganizationSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user) 
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user) 
    
    def destroy(self, request, *args, **kwargs):
        user = self.request.user
        instance = self.get_object()
        if user.role != 'admin':
            return Response(
                {
                    "detail": (
                        "You cannot delete an organization. "
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check for active users in the organization
        if User.objects.filter(is_active=True, organization=instance).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an organization with active users. "
                        "Please transfer the users or mark them as inactive."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        # Check for active tasks linked to active projects
        if Task.objects.filter(
            project__status=Project.Status.ACTIVE,
            organization=instance
        ).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an organization with active tasks "
                        "linked to active projects."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)