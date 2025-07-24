from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404
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
from django.db.models import Q, Prefetch
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework import serializers
from rest_framework import status
from django.db import transaction

import json
from datetime import datetime, date
today = date.today().isoformat()

from projects.models import Project, ProjectOrganization, Client, Task, Target, ProjectActivity, ProjectDeadline, ProjectActivityOrganization, ProjectDeadlineOrganization
from projects.serializers import ProjectListSerializer, ProjectDetailSerializer, TaskSerializer, TargetSerializer, ClientSerializer, ProjectActivitySerializer, ProjectDeadlineSerializer
from projects.utils import get_valid_orgs, ProjectPermissionHelper
from respondents.models import Interaction
from events.models import Event

class TaskViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TaskSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['indicator__code']
    search_fields = ['indicator__code', 'indicator__name']
    
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
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            queryset = queryset.filter(
                Q(organization=user.organization) | Q(organization__in=child_orgs)
            ).filter(
                project__status=Project.Status.ACTIVE
            )
            return queryset
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
            if not project.organizations.filter(id=organization.id).exists():
                raise ValidationError("Organization is not in this project.")

        elif role in ['meofficer', 'manager']:
            valid_orgs = get_valid_orgs(user)

            if not organization.id in valid_orgs:
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
        from events.models import DemographicCount
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
        if DemographicCount.objects.filter(task=instance).exists():
            return Response(
                {"detail": "You cannot delete a task that has event counts associated with it."},
                status=status.HTTP_409_CONFLICT
            )
        if Target.objects.filter(task=instance).exists():
            return Response(
                {"detail": "You cannot delete a task has targets associated with it."},
                status=status.HTTP_409_CONFLICT
            )

        # Restrict deletion to child organizations for non-admins
        if user.role in ['meofficer', 'manager']:
            is_child = ProjectOrganization.objects.filter(
                organization=instance.organization,
                parent_organization=user.organization
            ).exists()

            if not is_child:
                # This includes the case where instance.organization == user.organization
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
    filterset_fields = ['client', 'start', 'end', 'status', 'organizations']
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
        status_labels = [status.label for status in Project.Status]
        activity_categories = [cat for cat, _ in ProjectActivity.Category.choices]
        activity_category_labels = [cat.label for cat in ProjectActivity.Category]
        return Response({
            'statuses': statuses,
            'status_labels': status_labels,
            'activity_categories': activity_categories,
            'activity_category_labels': activity_category_labels
        })
    
    @action(detail=True, methods=['get'], url_path='get-related')
    def get_related(self, request, pk=None):
        project=self.get_object()
        user = request.user
        perm_manager = ProjectPermissionHelper(user, project)
        #get activities
        activities = ProjectActivity.objects.all()
        activities = perm_manager.filter_queryset(activities)
        activity_serializer = ProjectActivitySerializer(activities, many=True)
        #get deadlines
        deadlines = ProjectDeadline.objects.all()
        deadlines = perm_manager.filter_queryset(deadlines)
        deadline_serializer = ProjectDeadlineSerializer(deadlines, many=True)
        return Response({
            'activities': activity_serializer.data,
            'deadlines': deadline_serializer.data,
        })


    @action(detail=True, methods=['get'], url_path='get-orgs')
    def get_orgs(self, request, pk=None):
        from organizations.models import Organization
        from organizations.serializers import OrganizationListSerializer
        project = self.get_object()
        user = request.user
        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {"detail": "You do not have permission view this information."},
                status=status.HTTP_403_FORBIDDEN
            )
        in_project = ProjectOrganization.objects.filter(project=project)
        ids = [po.organization.id for po in in_project]
        if user.role != 'admin' and user.organization.id not in ids:
            return Response(
                {"detail": "You do not have permission view this information."},
                status=status.HTTP_403_FORBIDDEN
            )
        orgs = Organization.objects.exclude(id__in=ids)
        return Response({'results': OrganizationListSerializer(orgs, many=True).data})

    @action(detail=True, methods=['patch'], url_path='assign-subgrantee')
    def assign_child(self, request, pk=None):
        from organizations.models import Organization
        project = self.get_object()
        user = request.user
        parent_org_id = request.data.get('parent_id')
        child_org_id = request.data.get('child_id')
        if user.role not in ['meofficer', 'manager', 'admin']:
            return Response(
                {"detail": "You do not have permission to add a child organization."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        parent_org = get_object_or_404(Organization, id=parent_org_id)

        if user.role != 'admin':
            if parent_org != user.organization:
                return Response(
                    {"detail": "You may only assign children to your own organization."},
                    status=status.HTTP_403_FORBIDDEN
                )
        if not ProjectOrganization.objects.filter(organization=parent_org, project=project).exists():
            return Response(
                {"detail": "Parent organization not in the requested project."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        child_org = get_object_or_404(Organization, id=child_org_id)
        if parent_org == child_org:
            return Response({"detail": "An organization cannot be its own child."}, status=400)
            
        existing_link = ProjectOrganization.objects.filter(organization=child_org, project=project).first()
        if existing_link:
            if user.role != 'admin':
                return Response(
                    {"detail": "This organization is already associated with this project. Only admins can change its role within the hierarchy."},
                    status=status.HTTP_403_FORBIDDEN
                )
            # an admin making this request will automatically reassign if they are with another parent or top level
            existing_link.parent_organization = parent_org
            print(existing_link.parent_organization, existing_link.organization)
            existing_link.save()
            return Response(status=status.HTTP_200_OK)
        
        ProjectOrganization.objects.create(organization=child_org, parent_organization=parent_org, project=project)
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['patch'], url_path='promote-org')
    def promote_org(self, request, pk=None):
        from organizations.models import Organization
        project = self.get_object()
        user = request.user
        org_id = request.data.get('organization_id')
        if user.role != 'admin':
            return Response(
                {"detail": "You do not have permission to reassign organizations within a project."},
                status=status.HTTP_403_FORBIDDEN
            )
        org = Organization.objects.filter(id=org_id).first()
        if not org:
            return Response(
                {"detail": "Invalid child organization id provided.."},
                status=status.HTTP_400_BAD_REQUEST
            )
        org_link = ProjectOrganization.objects.filter(organization=org, project=project).first()
        if not org_link:
            return Response(
                {"detail": "The target organization is not associated with this project."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if org_link.parent_organization is None:
            return Response({"detail": "Organization is already a top-level member."}, status=200)
        org_link.parent_organization = None
        org_link.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

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
                if org_link.parent_organization != user.organization:
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
    

class TargetViewSet(RoleRestrictedViewSet):
    queryset = Target.objects.none()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    filterset_fields = ['task', 'task__organization', 'task__indicator', 'task__project']
    permission_classes = [IsAuthenticated]
    serializer_class = TargetSerializer
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        client_org = getattr(user, 'client_organization', None)
        
        if user.role == 'admin':
            queryset= Target.objects.all()
        elif user.role == 'client' and client_org:
            queryset= Target.objects.filter(task__project__client = client_org)
        else:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            queryset = Target.objects.filter(
                Q(task__organization=user.organization) | Q(task__organization__in=child_orgs)
            ).filter(
                task__project__status=Project.Status.ACTIVE
            )

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
            is_child = ProjectOrganization.objects.filter(
                organization=instance.task.organization,
                parent_organization=user.organization
            ).exists()

            if not is_child:
                # This includes the case where instance.organization == user.organization
                return Response(
                    {"detail": "You can only delete targets assigned to your child organizations."},
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

class ProjectActivityViewSet(RoleRestrictedViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    filterset_fields = ['category', 'project']
    search_fields = ['name', 'description', 'category'] 
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectActivitySerializer

    def get_queryset(self):
        user = self.request.user

        queryset = ProjectActivity.objects.all()
        perm_manager = ProjectPermissionHelper(user)

        return perm_manager.filter_queryset(queryset)

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()
        perm_manager = ProjectPermissionHelper(user)
        perm = perm_manager.destroy(instance)
        if not perm:
            return Response(
                {"detail": "You do not have permission to delete an activity."},
                status=status.HTTP_403_FORBIDDEN
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

class ProjectDeadlineViewSet(RoleRestrictedViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    filterset_fields = ['project']
    search_fields = ['name', 'description'] 
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectDeadlineSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = ProjectDeadline.objects.all()
        perm_manager = ProjectPermissionHelper(user)
        queryset = perm_manager.filter_queryset(queryset)

        # Add optimized prefetching of through table with related organization
        return queryset.prefetch_related(
            Prefetch(
                'projectdeadlineorganization_set',
                queryset=ProjectDeadlineOrganization.objects.select_related('organization'),
                to_attr='organizations'  # must match `source='organizations'` in serializer
            )
        )

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()
        perm_manager = ProjectPermissionHelper(user)
        perm = perm_manager.destroy(instance)
        if not perm:
            return Response(
                {"detail": "You do not have permission to delete an activity."},
                status=status.HTTP_403_FORBIDDEN
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['patch'], url_path='mark-complete')
    def mark_complete(self, request, pk=None):
        from organizations.models import Organization
        project_deadline = self.get_object()
        user = request.user
        
        organization_id = request.data.get('organization_id')
        organization = get_object_or_404(Organization, id=organization_id)

        if user.role != 'admin':
            perm_manager = ProjectPermissionHelper(user=user, project=project_deadline.project)
            if not perm_manager.verify_in_project():
                return Response(
                    {"detail": "You must be in this project to edit deadlines."},
                    status=status.HTTP_403_FORBIDDEN
                )
            org_link = ProjectOrganization.objects.filter(organization=organization).first()
            if user.organization != organization and org_link.parent_organization != user.organization:
                return Response(
                    {"detail": "You may not edit deadlines for other organizations."},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        dl_link = ProjectDeadlineOrganization.objects.filter(organization = organization).first()
        dl_link.completed= True
        dl_link.save()
        return Response(status=status.HTTP_204_NO_CONTENT)