from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.db.models import Q
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics
from rest_framework.decorators import action
from rest_framework import status
from django.db import transaction
from users.restrictviewset import RoleRestrictedViewSet
from events.models import Event, DemographicCount, EventTask, EventOrganization
from organizations.models import Organization
from projects.models import Project, Task
from indicators.models import Indicator, IndicatorSubcategory
from events.serializers import EventSerializer
from django.contrib.auth import get_user_model
User = get_user_model()

class EventViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['host', 'tasks', 'organizations']
    ordering_fields = ['name', 'host']
    search_fields = ['name', 'description', 'host'] 

    def get_queryset(self):
        queryset = super().get_queryset() 
        user = self.request.user
        if user.role == 'admin':
            return Event.objects.all()
        elif user.role == 'client':
            queryset = queryset.filter(tasks__project__client=user.client_organization)
        elif user.role in ['meofficer', 'manager']:
            queryset = queryset.filter(Q(host=user.organization) | Q(organizations = user.organization))
        else:
            return Event.objects.none()
        return queryset

    def create(self, request, *args, **kwargs):
        user = request.user
        host_id = request.data.get('host_id')

        if user.role != 'admin':
            if user.role not in ['meofficer', 'manager']:
                raise PermissionDenied("You do not have permission to edit events.")

            if not host_id:
                raise PermissionDenied("You must provide a host organization.")

            host = Organization.objects.filter(id=host_id).first()
            if not host:
                raise PermissionDenied("Host organization does not exist.")

            if user.organization != host and user.organization != host.parent_organization:
                raise PermissionDenied("You can only create an event where you are the host or its parent.")

        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        if user.role != 'admin':
            if user.role not in ['meofficer', 'manager']:
                raise PermissionDenied("You do not have permission to edit events.")

            if not instance.host:
                raise PermissionDenied("You must provide a host organization.")

            if user.organization != instance.host and user.organization != instance.host.parent_organization:
                raise PermissionDenied("You can only edit an event where you are the host or its parent.")
        return super().update(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
    
    
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
        if DemographicCount.objects.filter(event = instance).exists():
            return Response(
                {
                    "detail": (
                        "This event already has data associated with it, and cannot be deleted."
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @transaction.atomic  
    @action(detail=True, methods=['delete'], url_path='remove-organization/(?P<organization_id>[^/.]+)')
    def remove_organization(self, request, pk=None, organization_id=None):
        event = self.get_object()
        user = request.user

        if user.role != 'admin' and user.organization != event.host:
            return Response(
                {"detail": "You do not have permission to remove an organization from this event."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            org_link = EventOrganization.objects.get(event=event, organization__id=organization_id)

            if DemographicCount.objects.filter(event=event, organization=org_link.organization).exists():
                 return Response(
                        {"detail": "You cannot remove an organization from a project when they are associated with an existing count."},
                        status=status.HTTP_409_CONFLICT
                    )
            org_link.delete()
            return Response({"detail": f"Organization removed from event."}, status=status.HTTP_200_OK)

        except EventOrganization.DoesNotExist:
            return Response({"detail": "Organization not associated with this event."}, status=status.HTTP_404_NOT_FOUND)
    
    @transaction.atomic
    @action(detail=True, methods=['delete'], url_path='remove-task/(?P<task_id>[^/.]+)')
    def remove_task(self, request, pk=None, task_id=None):
        event = self.get_object()
        user = request.user

        if user.role != 'admin' and user.organization != event.host:
            return Response(
                {"detail": "You do not have permission to remove a task from this event."},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            task_link = EventTask.objects.get(event=event, task__id=task_id)

            if DemographicCount.objects.filter(event=event, task=task_link.task).exists():
                 return Response(
                        {"detail": "You cannot remove a task from an event when it is associated with an existing count."},
                        status=status.HTTP_409_CONFLICT
                    )
            task_link.delete()
            return Response({"detail": f"Task removed from event."}, status=status.HTTP_200_OK)

        except EventOrganization.DoesNotExist:
            return Response({"detail": "Task not associated with this event."}, status=status.HTTP_404_NOT_FOUND)
    
    @transaction.atomic
    @action(detail=True, methods=['patch'], url_path='update-counts')
    def update_counts(self, request, pk=None):
        event=self.get_object()
        user = request.user
        counts = request.data.get('counts', [])

        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {'detail': 'You do not have permission to edit event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if user.role != 'admin':
            if not event.host or event.host != user.organization or event.host.parent_organization != user.organization:
                return Response(
                {'detail': 'You do not have permission to edit counts for this event.'},
                status=status.HTTP_403_FORBIDDEN
            )
        task_ids = set(c['task_id'] for c in counts if 'task_id' in c)
        org_ids = set(c['organization_id'] for c in counts if 'organization_id' in c)
        subcat_ids = set(c['subcategory_id'] for c in counts if 'subcategory_id' in c)

        tasks = {t.id: t for t in Task.objects.filter(id__in=task_ids)}
        orgs = {o.id: o for o in Organization.objects.filter(id__in=org_ids)}
        subcategories = {s.id: s for s in IndicatorSubcategory.objects.filter(id__in=subcat_ids)}

        event_tasks = EventTask.objects.filter(event=event)
        event_orgs = EventOrganization.objects.filter(event=event)

        event_task_ids = set(event_tasks.values_list('task_id', flat=True))
        event_org_ids = set(event_orgs.values_list('organization_id', flat=True))

        valid_sexs = [sex for sex, _ in DemographicCount.Sex.choices]
        valid_age_ranges = [ar for ar, _ in DemographicCount.AgeRange.choices]
        valid_kp_types = [kp for kp, _ in DemographicCount.KeyPopulationType.choices]
        valid_disability_types = [dis for dis, _ in DemographicCount.DisabilityType.choices]
        valid_statuses = [s for s, _ in DemographicCount.Status.choices]
        valid_citizenships = [c for c, _ in DemographicCount.Citizenship.choices]

        to_update = []
        to_create = []

        for count in counts:
            amount = count.get('count')
            if not amount or amount in [0, '0', None]:
                continue
            
            if not str(amount).strip().isdigit():
                return Response({'detail': f'Provided Amount {amount} is invalid'}, status=400)
            amount = int(amount)
            
            sex = count.get('sex')
            if sex and sex not in valid_sexs:
                return Response({'detail': f'Invalid Sex: {sex}'}, status=400)

            age_range = count.get('age_range')
            if age_range and age_range not in valid_age_ranges:
                return Response({'detail': f'Invalid Age Range: {age_range}'}, status=400)

            kp_type = count.get('kp_type')
            if kp_type and kp_type not in valid_kp_types:
                return Response({'detail': f'Invalid KP Type: {kp_type}'}, status=400)

            disability_type = count.get('disability_type')
            if disability_type and disability_type not in valid_disability_types:
                return Response({'detail': f'Invalid Disability Type: {disability_type}'}, status=400)

            citizenship = count.get('citizenship')
            if citizenship and citizenship not in valid_citizenships:
                return Response({'detail': f'Invalid Citizenship: {citizenship}'}, status=400)

            status_name = count.get('status')
            if status_name and status_name not in valid_statuses:
                return Response({'detail': f'Invalid Status: {status_name}'}, status=400)

            hiv_status = count.get('hiv_status')
            if hiv_status in [True, 'true', 1, '1']:
                hiv_status = True
            elif hiv_status in [False, 'false', 0, '0']:
                hiv_status = False
            elif hiv_status is not None:
                return Response({'detail': f'Invalid HIV Status: {hiv_status}'}, status=400)
            
            pregnancy = count.get('pregnancy')
            if pregnancy in ['true', True, 1, '1']:
                pregnancy = True
            elif pregnancy in ['false', False, 0, '0']:
                pregnancy = False 
            elif pregnancy is not None:
                return Response({'detail': f'Invalid Pregnancy: {pregnancy}'}, status=400)

            task_id = count.get('task_id')
            subcategory = None
            task = None
            if task_id:
                task = tasks.get(task_id)
                if not task or task.id not in event_task_ids:
                    return Response({'detail': f'Invalid Task: {task_id}'}, status=400)
                if task.indicator.subcategories.exists():
                    subcategory_id = count.get('subcategory_id')
                    if not subcategory_id:
                        return Response({'detail': f'Task {task.indicator.name} requires a subcategory.'}, status=400)
                    subcategory = subcategories.get(subcategory_id)
                    if not subcategory or subcategory not in task.indicator.subcategories.all():
                        return Response({'detail': f'Subcategory id {subcategory_id} is not valid for task {task.indicator.name}'}, status=400)
                    

            org_id = count.get('organization_id')
            org = None
            if org_id:
                org = orgs.get(org_id)
                if not org or org.id not in event_org_ids:
                    return Response({'detail': f'Invalid Organization: {org_id}'}, status=400)


            existing = DemographicCount.objects.filter(
                event=event, sex=sex, age_range=age_range, citizenship=citizenship,
                hiv_status=hiv_status, pregnancy=pregnancy, disability_type=disability_type,
                kp_type=kp_type, task=task, subcategory=subcategory, organization=org,
                status=status_name
            )
            if existing.exists():
                instance = existing.first()
                if instance.count != amount:
                    instance.count = amount
                    instance.updated_by = user
                    to_update.append(instance)
            else:
                instance = DemographicCount(
                    event=event, count=amount, sex=sex, age_range=age_range, citizenship=citizenship,
                    hiv_status=hiv_status, pregnancy=pregnancy, disability_type=disability_type,
                    kp_type=kp_type, task=task, subcategory=subcategory, organization=org,
                    status=status_name, created_by=user
                )
                to_create.append(instance)
        DemographicCount.objects.bulk_update(to_update, ['count', 'updated_by'])
        DemographicCount.objects.bulk_create(to_create)

        return Response({
            'detail': f'{len(to_update)} updated, {len(to_create)} created.'
        }, status=200)
            