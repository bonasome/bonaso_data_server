from django.shortcuts import render, redirect
from django.db.models import Q

from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from users.restrictviewset import RoleRestrictedViewSet
from organizations.models import Organization
from projects.models import Project, Task, ProjectOrganization
from organizations.serializers import OrganizationListSerializer, OrganizationSerializer
from projects.utils import get_valid_orgs

from django.contrib.auth import get_user_model
User = get_user_model()

class OrganizationViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = OrganizationSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    filterset_fields = ['project', 'indicator']
    ordering_fields = ['name']
    search_fields = ['name'] 
    def get_queryset(self):

        user = self.request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)
        if role == 'admin':
            queryset = Organization.objects.all()
        elif role in ['meofficer', 'manager']:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization__id', flat=True)

            queryset = Organization.objects.filter(
                Q(id=user.organization.id) | Q(id__in=child_orgs)
            )
            return queryset
        else:
            return Organization.objects.filter(id=user.organization.id)
        
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(projectorganization__project__id=project_id)
        exclude_project_id = self.request.query_params.get('exclude_project')
        if exclude_project_id:
            queryset = queryset.exclude(projectorganization__project__id=exclude_project_id)
        exclude_event_id = self.request.query_params.get('exclude_event')
        if exclude_event_id:
            queryset = queryset.exclude(eventorganization__event__id=exclude_event_id)
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
                {"detail": ("You cannot delete an organization. ")},
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