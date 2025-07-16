from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework import generics
from django.db.models import Q
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework import serializers
from rest_framework import status
from django.db import transaction

import json
from datetime import datetime, date
today = date.today().isoformat()

from projects.models import Project, ProjectIndicator, ProjectOrganization, Client, Task, Target
from projects.serializers import ProjectListSerializer, ProjectDetailSerializer, TaskSerializer, TargetSerializer, ClientSerializer
from respondents.models import Interaction
from events.models import Event

class TaskViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TaskSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['indicator__code']
    search_fields = ['indicator__code', 'indicator__name']
    filterset_fields = ['project', 'organization', 'indicator', 'indicator__indicator_type']
    
    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        user_org = getattr(user, 'organization', None)
        user_client = getattr(user, 'client_organization', None)
        queryset = Task.objects.all()

        org_param = self.request.query_params.get('organization')
        if org_param:
            queryset = queryset.filter(organization__id=org_param)
            
        project_param = self.request.query_params.get('project')
        if project_param:
            queryset = queryset.filter(project__id=project_param)

        type_param = self.request.query_params.get('indicator_type')
        if type_param:
            queryset = queryset.filter(indicator__indicator_type=type_param)

        event_param = self.request.query_params.get('event')
        if event_param:
            try:
                event = Event.objects.get(id=event_param)
            except Event.DoesNotExist:
                return queryset.none()

            queryset = queryset.exclude(eventtask__event__id=event_param)
            queryset = queryset.filter(Q(organization__in=event.organizations.all()) | Q(organization=event.host))

        if role == 'admin':
            return queryset
        elif role in ['meofficer', 'manager'] and user_org:
            return queryset.filter(Q(organization=user_org) | Q(organization__parent_organization=user_org), project__status=Project.Status.ACTIVE)
        elif role in ['client'] and user_client:
            return queryset.filter(project__client=user_client)
        elif role in ['data_collector'] and user_org:
            return queryset.filter(organization=user_org, project__status=Project.Status.ACTIVE)
        else:
            return Task.objects.none()

    def create(self, request, *args, **kwargs):
        from organizations.models import Organization
        from indicators.models import Indicator

        user = request.user
        role = getattr(user, 'role', None)
        user_org = getattr(user, 'organization', None)

        data = request.data
        org_id = data.get('organization_id')
        indicator_id = data.get('indicator_id')
        project_id = data.get('project_id')

        if not role or not user_org:
            raise PermissionDenied("You do not have permission to perform this action.")

        if not all([org_id, indicator_id, project_id]):
            raise ValidationError("All of organization_id, indicator_id, and project_id are required.")

        try:
            org_id = int(org_id)
            indicator_id = int(indicator_id)
            project_id = int(project_id)
        except (TypeError, ValueError):
           raise ValidationError("IDs must be valid integers.")

        try:
            organization = Organization.objects.get(id=org_id)
            indicator = Indicator.objects.get(id=indicator_id)
            project = Project.objects.get(id=project_id)
        except (Organization.DoesNotExist, Indicator.DoesNotExist, Project.DoesNotExist):
            raise ValidationError("One or more provided IDs are invalid.")
        if Task.objects.filter(organization=organization, indicator=indicator, project=project).exists():
            raise ValidationError('This task already exists.')
        if role == 'admin':
            if not project.organizations.filter(id=organization.id).exists() or \
            not project.indicators.filter(id=indicator.id).exists():
                raise ValidationError("Organization/indicator are not in this project.")

        elif role in ['meofficer', 'manager']:
            # Validate org/indicator/project assignment
            if not Organization.objects.filter(id=org_id, parent_organization=user_org).exists():
                raise PermissionDenied('You may only assign tasks to your child organizations.')

            if not Task.objects.filter(organization=user_org, indicator=indicator).exists():
                raise PermissionDenied('You may only assign indicators you also have.')

            if not Project.objects.filter(id=project_id, organizations=user_org).exists():
                raise PermissionDenied('You can only assign tasks to projects you are part of.')

        else:
            raise PermissionDenied('You do not have permission to perform this action.')

        # Check prerequisites (shared by both roles)
        prereqs = getattr(indicator, 'prerequisites', None)
        for prereq in prereqs.all():
            if prereq and not Task.objects.filter(project=project, organization=organization, indicator=prereq).exists():
                raise ValidationError(
                    f"This task's indicator has a prerequisite '{prereq.name}'. Please assign that indicator as a task first."
                )

        task = Task.objects.create(
            project=project,
            organization=organization,
            indicator=indicator,
            created_by=user
        )
        return Response(self.get_serializer(task).data, status=201)

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        # Role check
        if user.role not in ['admin', 'meofficer', 'manager']:
            return Response(
                {"detail": "You do not have permission to delete a task."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Prevent deletion if task has interactions
        if Interaction.objects.filter(task=instance).exists():
            return Response(
                {"detail": "You cannot delete a task that has interactions associated with it."},
                status=status.HTTP_409_CONFLICT
            )

        # Restrict deletion to child organizations for non-admins
        if user.role in ['meofficer', 'manager']:
            if instance.organization.parent_organization_id != user.organization_id:
                return Response(
                    {"detail": "You can only delete tasks assigned to your child organizations."},
                    status=status.HTTP_403_FORBIDDEN
                )
        if Task.objects.filter(indicator__prerequisites = instance.indicator, project=instance.project, organization=instance.organization).exists():
            return Response(
                    {"detail": "You cannot remove this task since it is a prerequisite for one or more tasks."},
                    status=status.HTTP_409_CONFLICT
                )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)  
    
class ProjectViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    filterset_fields = ['client', 'start', 'end', 'status', 'indicators', 'organizations']
    ordering_fields = ['name','start', 'end', 'client']
    search_fields = ['name', 'description'] 
    queryset = Project.objects.none()
    serializer_class = ProjectDetailSerializer
    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
        else:
            return ProjectDetailSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)
        client_org = getattr(user, 'client_organization', None)
        if role == 'admin':
            queryset = Project.objects.all()
            status = self.request.query_params.get('status')
            if status:
                queryset = queryset.filter(status=status)
            return queryset
        elif role == 'client' and client_org:
            return Project.objects.filter(client=client_org)
        elif role and org:
            return Project.objects.filter(organizations=org, status=Project.Status.ACTIVE)

        return Project.objects.none()
    
    def create(self, request, *args, **kwargs):
        if request.user.role != 'admin':
            raise PermissionDenied("Only admins can create projects.")
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
    
    def partial_update(self, request, *args, **kwargs):
        from organizations.models import Organization

        user = request.user
        instance = self.get_object()

        if user.role != 'admin':
            if user.role in ['meofficer', 'manager']:
                if instance.status == Project.Status.ACTIVE:
                    allowed_keys = ['organization_id']
                    if not any(k in request.data for k in allowed_keys):
                        raise PermissionDenied("Only admins can edit projects.")

                    new_org_ids = request.data.get('organization_id', [])
                    if not isinstance(new_org_ids, list):
                        new_org_ids = [new_org_ids]

                    existing_org_ids = set(instance.organizations.values_list('id', flat=True))
                    new_orgs = Organization.objects.filter(id__in=new_org_ids).exclude(id__in=existing_org_ids)

                    # Check for invalid orgs not subgrantees of user's org
                    invalid_orgs = [org for org in new_orgs if org.parent_organization != user.organization]
                    if invalid_orgs:
                        raise PermissionDenied("You may only add your subgrantees.")

                    # Check if all requested IDs exist
                    found_org_ids = set(org.id for org in new_orgs)
                    missing_org_ids = set(new_org_ids) - found_org_ids - existing_org_ids
                    if missing_org_ids:
                        return Response({"detail": f"Organizations not found: {missing_org_ids}"}, status=400)

                    instance.organizations.add(*new_orgs)

                    # Return updated data
                    serializer = ProjectDetailSerializer(instance, context=self.get_serializer_context())
                    return Response(serializer.data)

            else:
                raise PermissionDenied("Only admins can edit active projects.")

        # Admin users get normal partial update behavior
        return super().partial_update(request, *args, **kwargs)
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        # Only admins can delete
        if user.role != 'admin':
            return Response(
                {"detail": "You cannot delete a project."},
                status=status.HTTP_403_FORBIDDEN 
            )

        # Prevent deletion of active projects
        if instance.status == Project.Status.ACTIVE:
            return Response(
                {
                    "detail": (
                        "You cannot delete an active project. "
                        "If necessary, please mark it as planned or on hold first."
                    )
                },
                status=status.HTTP_409_CONFLICT
            )
        if Interaction.objects.filter(task__project = instance).exists():
            return Response(
                {
                    "detail": (
                        "This project has interactions associated with it, and therefore cannot be deleted."
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
        
    @action(detail=False, methods=['get'], url_path='meta')
    def filter_options(self, request):
        statuses = [status for status, _ in Project.Status.choices]
        clients = Client.objects.values('id', 'name')
        return Response({
            'statuses': statuses,
            'clients': list(clients) if clients else None,
        })
    @action(detail=True, methods=['delete'], url_path='remove-organization/(?P<organization_id>[^/.]+)')
    def remove_organization(self, request, pk=None, organization_id=None):
        project = self.get_object()
        user = request.user

        # Permission check
        if user.role not in ['meofficer', 'manager', 'admin']:
            return Response(
                {"detail": "You do not have permission to remove an organization from a project."},
                status=status.HTTP_403_FORBIDDEN
            )
        try:
            org_link = ProjectOrganization.objects.get(project=project, organization__id=organization_id)

            # Additional org-level check for non-admins
            if user.role in ['meofficer', 'manager']:
                if org_link.organization.parent_organization_id != user.organization_id:
                    return Response(
                        {"detail": "You can only remove child organizations of your own organization."},
                        status=status.HTTP_403_FORBIDDEN
                    )
            if Interaction.objects.filter(task__organization__id = org_link.organization.id).exists():
                 return Response(
                        {"detail": "You cannot remove an organization from a project when they have active tasks."},
                        status=status.HTTP_409_CONFLICT
                    )
            count, _ = Task.objects.filter(project=project, organization=org_link.organization).delete()
            org_link.delete()
            return Response({"detail": f"Organization and {count} related inactive tasks removed from project."}, status=status.HTTP_200_OK)

        except ProjectOrganization.DoesNotExist:
            return Response({"detail": "Organization not associated with this project."}, status=status.HTTP_404_NOT_FOUND)
    
    @transaction.atomic
    @action(detail=True, methods=['delete'], url_path='remove-indicator/(?P<indicator_id>[^/.]+)')
    def remove_indicator(self, request, pk=None, indicator_id=None):
        user = request.user
        if user.role != 'admin':
            return Response(
                {"detail": "You do not have permission to remove an indicator from a project."},
                status=status.HTTP_403_FORBIDDEN
            )

        project = self.get_object()

        try:
            indicator_link = ProjectIndicator.objects.get(project=project, indicator__id=indicator_id)

            if Interaction.objects.filter(task__indicator=indicator_link.indicator).exists():
                return Response(
                    {"detail": "You cannot remove an indicator from a project when it has active tasks."},
                    status=status.HTTP_409_CONFLICT
                )

            if ProjectIndicator.objects.filter(project=project, indicator__prerequisites__id=indicator_id).exists():
                return Response(
                    {"detail": "You cannot remove this indicator since it is a prerequisite for other indicators in this project. Please remove those first."},
                    status=status.HTTP_409_CONFLICT
                )

            count, _ = Task.objects.filter(project=project, indicator=indicator_link.indicator).delete()
            indicator_link.delete()

            return Response(
                {"detail": f"Indicator removed along with {count} associated tasks."},
                status=status.HTTP_200_OK
            )

        except ProjectIndicator.DoesNotExist:
            return Response({"detail": "Indicator not found."}, status=status.HTTP_404_NOT_FOUND)
    

class TargetViewSet(RoleRestrictedViewSet):
    queryset = Target.objects.none()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    filterset_fields = ['task', 'task__organization', 'task__indicator', 'task__project']
    permission_classes = [IsAuthenticated]
    serializer_class = TargetSerializer
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)
        client_org = getattr(user, 'client_organization', None)
        if not role or not org:
            return Target.objects.none()
        
        if role == 'admin':
            queryset= Target.objects.all()
        elif role == 'client' and client_org:
            queryset= Target.objects.filter(task__project__client = client_org)
        else:
            queryset= Target.objects.filter(Q(task__organization=org) | Q(task__organization__parent_organization=org))
            queryset = queryset.filter(task__project__status=Project.Status.ACTIVE)

        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start:
            queryset = queryset.filter(start__gte=start)
        if end:
            queryset = queryset.filter(end__lte=end)

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        # Role check
        if user.role not in ['admin', 'meofficer', 'manager']:
            return Response(
                {"detail": "You do not have permission to delete a target."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Restrict deletion to child organizations for non-admins
        if user.role in ['meofficer', 'manager']:
            if instance.task.organization.parent_organization_id != user.organization_id:
                return Response(
                    {"detail": "You can only delete targets from your child organizations."},
                    status=status.HTTP_403_FORBIDDEN
                )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    

class ClientViewSet(RoleRestrictedViewSet):
    queryset = Client.objects.all()
    filter_backends = [filters.SearchFilter, OrderingFilter]
    filterset_fields = ['name', 'full_name']
    search_fields = ['name', 'full_name'] 
    permission_classes = [IsAuthenticated]
    serializer_class = ClientSerializer
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', None)
        
        if role != 'admin':
            queryset= Client.objects.none()

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        # Role check
        if user.role not in ['admin']:
            return Response(
                {"detail": "You do not have permission to delete a client."},
                status=status.HTTP_403_FORBIDDEN
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)