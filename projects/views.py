from django.shortcuts import render, redirect
from django.shortcuts import get_object_or_404
from django.db.models import Q, Prefetch
from django.db import transaction

from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from rest_framework import status

from datetime import date

from users.restrictviewset import RoleRestrictedViewSet

from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from projects.models import Project, ProjectOrganization, Client, Task, Target, ProjectActivity, ProjectDeadline, ProjectActivityOrganization, ProjectDeadlineOrganization
from projects.serializers import ProjectListSerializer, ProjectDetailSerializer, TaskSerializer, TargetSerializer, ClientSerializer, ProjectActivitySerializer, ProjectDeadlineSerializer
from projects.utils import ProjectPermissionHelper, test_child_org
from respondents.models import Interaction
from respondents.utils import get_enum_choices
from events.models import Event, DemographicCount
from messaging.models import Announcement
from messaging.serializers import AnnouncementSerializer

today = date.today().isoformat()


    
class ProjectViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    filterset_fields = ['client', 'start', 'end', 'status', 'organizations']
    ordering_fields = ['name','start', 'end', 'client']
    search_fields = ['name', 'description'] 

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
        elif role == 'client' and client_org:
            queryset = Project.objects.filter(client=client_org)
        elif role in ['meofficer', 'manager']:
            queryset =  Project.objects.filter(organizations=org, status=Project.Status.ACTIVE)
        else: 
            queryset = Project.objects.none()
        
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        start = self.request.query_params.get('start')
        if start:
            queryset = queryset.filter(start__gte=start)

        end = self.request.query_params.get('end')
        if end:
            queryset = queryset.filter(end__lte=end)

        indicator_param = self.request.query_params.get('indicator')
        if indicator_param:
            valid_ids = Task.objects.filter(indicator__id=indicator_param).distinct().values_list('project__id', flat=True)
            queryset = queryset.filter(id__in=valid_ids)

        return queryset

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        '''
        Only admins can delete projects, a
        '''
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
                {"detail": ("You cannot delete an active project. If necessary, please mark it as planned or on hold first.")},
                status=status.HTTP_409_CONFLICT
            )
        #as well as projects that have an interaction or event count associated with them
        if Interaction.objects.filter(task__project = instance).exists() or DemographicCount.objects.filter(task__project=instance).exists():
            return Response(
                {"detail": ("This project has data associated with it, and therefore cannot be deleted.")},
                status=status.HTTP_409_CONFLICT
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['get'], url_path='meta')
    def get_meta(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "statuses": get_enum_choices(Project.Status),
            "activity_categories": get_enum_choices(ProjectActivity.Category),
        })
    
    @action(detail=True, methods=['get'], url_path='get-related')
    def get_related(self, request, pk=None):
        '''
        One stop shop to get related materials (i.e., activites/deadlines)
        '''
        project=self.get_object()
        user = request.user
        perm_manager = ProjectPermissionHelper(user, project)

        #get activities
        activities = ProjectActivity.objects.filter(project=project)
        activities = perm_manager.filter_queryset(activities)
        activity_serializer = ProjectActivitySerializer(activities, many=True)

        #get deadlines
        deadlines = ProjectDeadline.objects.filter(project=project)
        deadlines = perm_manager.filter_queryset(deadlines)
        deadline_serializer = ProjectDeadlineSerializer(deadlines, many=True)

        #get announcements
        announcements = Announcement.objects.filter(project=project)
        announcements = perm_manager.filter_queryset(announcements)
        announcement_serializer = AnnouncementSerializer(announcements, many=True, context={'request': request})

        return Response({
            'activities': activity_serializer.data,
            'deadlines': deadline_serializer.data,
            'announcements': announcement_serializer.data,
        })

    @action(detail=True, methods=['get'], url_path='get-orgs')
    def get_orgs(self, request, pk=None):
        '''
        This is used by the frontend to basically pull a list of orgs not already in the project for when
        adding organizations to a project.
        '''
        project = self.get_object()
        user = request.user
        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {"detail": "You do not have permission view this information."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        #get a list in the project
        in_project = ProjectOrganization.objects.filter(project=project)
        #make sure their org is in the project if not an admin
        ids = [po.organization.id for po in in_project]
        if user.role != 'admin' and user.organization.id not in ids:
            return Response(
                {"detail": "You do not have permission view this information."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        #exclude already included
        queryset = Organization.objects.exclude(id__in=ids)
        search_term = request.query_params.get('search')
        if search_term:
            queryset = queryset.filter(
                Q(name__icontains=search_term) |
                Q(full_name__icontains=search_term)
            )
            
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = OrganizationListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = OrganizationListSerializer(queryset, many=True)
        return Response(serializer.data)


    '''
    To help manage the flow of users adding/remove organizations cleanly, split it into a few actions
    '''
    @action(detail=True, methods=['patch'], url_path='assign-subgrantee')
    def assign_child(self, request, pk=None):
        '''
        Allows a user (admin or higher role) to add an organization (or organizations) as a subgrantee, 
        assuming a parent_id and a list of child_ids is sent.
        '''
        project = self.get_object()
        user = request.user
        parent_org_id = request.data.get('parent_id') #send as a singular ID
        child_org_ids = request.data.get('child_ids', []) #send as a list of ids
        
        if user.role not in ['meofficer', 'manager', 'admin']:
            return Response(
                {"detail": "You do not have permission to add a child organization."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if not parent_org_id or not child_org_ids:
            return Response(
                {"detail": "Parent ID and Child ID are both required."},
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
        added=[]
        reassigned=[]
        #loop through each id provided and runs some checks, then create
        for child_org_id in child_org_ids:
            child_org = get_object_or_404(Organization, id=child_org_id)

            #disallow circular dependencies
            if parent_org == child_org:
                return Response({"detail": "An organization cannot be its own child."}, status=400)

            #prevent adding orgs that are already in the project if the user is not an admin 
            existing_link = ProjectOrganization.objects.filter(organization=child_org, project=project).first()
            if existing_link:
                if user.role != 'admin':
                    return Response(
                        {"detail": "This organization is already associated with this project. Only admins can change its role within the hierarchy."},
                        status=status.HTTP_403_FORBIDDEN
                    )
                # an admin making this request will automatically reassign if they are with another parent or top level
                existing_link.parent_organization = parent_org
                existing_link.save()
                reassigned.append({'id': existing_link.organization.id, 'name': existing_link.organization.name})
            else:
                new_link = ProjectOrganization.objects.create(organization=child_org, parent_organization=parent_org, project=project)
                added.append({'id': new_link.organization.id, 'name': new_link.organization.name})
        return Response(
            {'added': added,
            'reassigned': reassigned},
            status=status.HTTP_200_OK
        )
    
    
    @action(detail=True, methods=['patch'], url_path='promote-org')
    def promote_org(self, request, pk=None):
        '''
        Admins are the only ones that do this, but create a reverse action that allows an admin to make an organization
        free of its parent if there was a mistake or whatever
        '''
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
        '''
        Allow admins to remove organizations from a project or parents to remove children if a mistake was made.
        '''
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
            #prevent removal if there is data associated with this org for this project
            if Interaction.objects.filter(task__organization__id = org_link.organization.id
                ).exists() or DemographicCount.objects.filter(task__organization__id=org_link.organization.id
                ).exists():
                 return Response(
                        {"detail": "You cannot remove an organization from a project when they have active tasks."},
                        status=status.HTTP_409_CONFLICT
                    )
            count, _ = Task.objects.filter(project=project, organization=org_link.organization).delete()
            org_link.delete()
            return Response({"detail": f"Organization and {count} related inactive tasks removed from project."}, status=status.HTTP_200_OK)

        except ProjectOrganization.DoesNotExist:
            return Response({"detail": "Organization not associated with this project."}, status=status.HTTP_404_NOT_FOUND)

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

        exclude_type_param = self.request.query_params.get('exclude_indicator_type')
        if exclude_type_param:
            queryset = queryset.exclude(indicator__indicator_type=type_param)

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
            #filter other roles to only see their own org or child orgs for active projects
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
            #clients can only see if it's their project
            return queryset.filter(project__client=user_client)
        elif role in ['data_collector'] and user_org:
            #dc can only see their own organization
            return queryset.filter(organization=user_org, project__status=Project.Status.ACTIVE)
        else:
            return Task.objects.none()

    def destroy(self, request, *args, **kwargs):
        '''
        Allow deleting tasks if its for a child org/the user is an admin and the task does not have any 
        associated data (interaction, count, target).
        '''
        user = request.user
        instance = self.get_object()

        # Role check
        if user.role not in ['admin', 'meofficer', 'manager']:
            return Response(
                {"detail": "You do not have permission to delete a task."},
                status=status.HTTP_403_FORBIDDEN
            )
        if user.role != 'admin' and not test_child_org(user, instance.organization, instance.project):
            return Response(
                    {"detail": "You can only delete tasks assigned to your child organizations."},
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
                
        if Task.objects.filter(indicator__prerequisites = instance.indicator, project=instance.project, organization=instance.organization).exists():
            return Response(
                    {"detail": "You cannot remove this task since it is a prerequisite for one or more tasks."},
                    status=status.HTTP_409_CONFLICT
                )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)  
    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create_task(self, request):
        organization_id = request.data.get('organization_id')
        project_id = request.data.get('project_id')
        indicator_ids = request.data.get('indicator_ids', [])
        print(request.data, organization_id, project_id, indicator_ids)
        if not organization_id or not project_id or not indicator_ids:
            return Response(
                {"detail": "You must provide an organization, project, and at least one indicator to create a task."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created = []
        skipped = []
        for indicator_id in indicator_ids:
            existing_task = Task.objects.filter(indicator_id=indicator_id, project_id=project_id, organization_id=organization_id).first()
            if existing_task:
                skipped.append(f'Task "{str(existing_task)}" already exists and was skipped.')
                continue
            serializer = self.get_serializer(data={
                'organization_id': organization_id,
                'indicator_id': indicator_id,
                'project_id': project_id,
            }, context={'request': request})

            serializer.is_valid(raise_exception=True)
            serializer.save()
            created.append(serializer.data)

        return Response({
            "created": created,
            "skipped": skipped
        }, status=status.HTTP_201_CREATED)

class TargetViewSet(RoleRestrictedViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    filterset_fields = ['task', 'task__organization', 'task__indicator', 'task__project']
    search_fields = ['task__indicator__code', 'task__indicator__name']
    permission_classes = [IsAuthenticated]
    serializer_class = TargetSerializer

    def get_queryset(self):
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

        if user.role != 'admin' and not test_child_org(user, instance.task.organization, instance.task.project):
            return Response(
                {"detail": "You do not have permission to delete this target."},
                status=status.HTTP_403_FORBIDDEN
            )
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    

class ClientViewSet(RoleRestrictedViewSet):
    filter_backends = [filters.SearchFilter, OrderingFilter]
    filterset_fields = ['name', 'full_name']
    search_fields = ['name', 'full_name'] 
    permission_classes = [IsAuthenticated]
    serializer_class = ClientSerializer

    def get_queryset(self):
        '''
        Only admins should be managing this.
        '''
        user = self.request.user
        role = getattr(user, 'role', None)
        queryset = Client.objects.all()
        if role != 'admin':
            queryset= Client.objects.none()
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        '''
        Admins can delete as long as they don't own a project.
        '''
        user = request.user
        instance = self.get_object()

        # Role check
        if user.role not in ['admin']:
            return Response(
                {"detail": "You do not have permission to delete a client."},
                status=status.HTTP_403_FORBIDDEN
            )
        if Project.objects.filter(client=instance).exists():
            return Response(
                {"detail": "You cannot delete a client that owns a project."},
                status=status.HTTP_409_CONFLICT
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
        '''
        Can destroy own activities/admins can destroy all
        '''
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
        '''
        Can destroy own deadlines/admins can destroy all
        '''
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
        '''
        Simple action to mark a deadline as complete
        '''
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
        
        dl_link = ProjectDeadlineOrganization.objects.get_or_create(deadline=project_deadline, organization=organization)[0]
        dl_link.completed= True
        dl_link.updated_by = user
        dl_link.save()
        return Response(status=status.HTTP_204_NO_CONTENT)