from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Q, Exists, OuterRef
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework import status

from datetime import date
from django.utils.timezone import now
from collections import defaultdict

from users.restrictviewset import RoleRestrictedViewSet
from django.contrib.auth import get_user_model
User = get_user_model()

from events.models import Event, EventTask, EventOrganization
from events.serializers import EventSerializer
from organizations.models import Organization
from projects.models import Task, ProjectOrganization
from respondents.utils import get_enum_choices


class EventViewSet(RoleRestrictedViewSet):
    '''
    Viewset that handles all endpoints related to events and demograhic counts. 
    '''
    permission_classes = [IsAuthenticated]
    serializer_class = EventSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['event_type', 'status', 'host', 'start', 'end']
    ordering_fields = ['name', 'host']
    search_fields = ['name', 'description', 'host'] 
    filterset_fields = ['event_type']

    def get_queryset(self):
        '''
        Admins can see all, clients can see events if they are related to a task, higher roles can see 
        events they/their child orgs host or events they are a participant in. Lower roles can't see anything.
        '''
        user = self.request.user

        #admin can see all
        if user.role == 'admin':
            queryset = Event.objects.all()
        #client can see any event that has counts relevent to their projects
        elif user.role == 'client':
            queryset = Event.objects.filter(Q(tasks__project__client=user.client_organization) | Q(project__client=user.client_organization))
            queryset=queryset.distinct()
        #higher roles can see event where they are the host, their child is the host, or they are a participant
        elif user.role in ['meofficer', 'manager']:
            my_projects = ProjectOrganization.objects.filter(
                organization=user.organization
            ).values_list('project_id', flat=True)

            # Base: org is directly host or participant
            base_q = Q(host=user.organization) | Q(organizations=user.organization)

            # Child-host relationships (parent-child link within a project)
            project_child_rels = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            )

            # Events where a child org is the host and both share a project
            child_host_q = Q(
                Exists(
                    project_child_rels.filter(
                        organization=OuterRef('host'),
                        project=OuterRef('project')
                    )
                )
            )

            # Events where a child org hosts but project comes via tasks
            child_host_task_q = Q(
                Exists(
                    project_child_rels.filter(
                        organization=OuterRef('host'),
                        project=OuterRef('tasks__project')
                    )
                )
            )

            queryset = Event.objects.filter(
                base_q | child_host_q | child_host_task_q
            ).distinct()
        else:
            return Event.objects.none()

        #custom filter params
        host_param = self.request.query_params.get('host')
        if host_param:
            queryset=queryset.filter(host__id=host_param)
        status_param = self.request.query_params.get('status')
        if status_param:
            queryset=queryset.filter(status=status_param)
        start_param = self.request.query_params.get('start')
        if start_param:
            queryset = queryset.filter(start__gte=start_param)

        end_param = self.request.query_params.get('end')
        if end_param:
            queryset = queryset.filter(end__lte=end_param)
        project_param = self.request.query_params.get('project')
        if project_param:
            queryset = queryset.filter(Q(tasks__project_id=project_param) | Q(project_id=project_param)).distinct()

        return queryset
    
    @action(detail=False, methods=['get'], url_path='meta')
    def get_meta(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "event_types": get_enum_choices(Event.EventType),
            "statuses": get_enum_choices(Event.EventStatus),
        })

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        '''
        Only admins can delete events and events that have counts attached should be protected.
        '''
        user = request.user
        instance = self.get_object()
        # Only admins can delete
        if user.role != 'admin':
            return Response(
                {"detail": "You cannot delete an event."},
                status=status.HTTP_403_FORBIDDEN 
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=False, methods=['get'], url_path='gantt')
    def get_gantt(self, request):
        user = request.user
        project_id = request.query_params.get('project')

        if not project_id:
            return Response({'detail': 'Project ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Only fetch events linked to this project (directly or through tasks)
        events = Event.objects.filter(
            Q(project_id=project_id) |
            Q(tasks__project_id=project_id)
        ).filter(
            Q(host=user.organization) | Q(organizations=user.organization)
        ).distinct()

        data = []
        for event in events:
            data.append({
                'id': event.id,
                'name': event.name,
                'start': event.start,
                'end': event.end,
                'category': event.event_type,
                'host': event.host.name if event.host else None,
            })

        return Response({'data': data}, status=status.HTTP_200_OK)
