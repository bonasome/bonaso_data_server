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
from events.serializers import EventSerializer, DCSerializer
from django.contrib.auth import get_user_model
from collections import defaultdict
from datetime import date

User = get_user_model()

class EventViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['event_type']
    ordering_fields = ['name', 'host']
    search_fields = ['name', 'description', 'host'] 
    filterset_fields = ['event_type']

    def get_queryset(self):
        user = self.request.user

        if user.role == 'admin':
            queryset = Event.objects.all()
        elif user.role == 'client':
            queryset = Event.objects.filter(tasks__project__client=user.client_organization)
        elif user.role in ['meofficer', 'manager']:
            queryset = Event.objects.filter(
                Q(host=user.organization) | Q(organizations=user.organization)
            ).distinct()
        else:
            return Event.objects.none()

        org_param = self.request.query_params.get('organization')
        if org_param:
            queryset = queryset.filter(
                Q(organizations__id=org_param) | Q(host__id=org_param)
            )

        ind_param = self.request.query_params.get('indicator')
        if ind_param:
            queryset = queryset.filter(tasks__indicator__id=ind_param)

        start_param = self.request.query_params.get('start')
        if start_param:
            queryset = queryset.filter(event_date__gte=start_param)

        end_param = self.request.query_params.get('end')
        if end_param:
            queryset = queryset.filter(event_date__lte=end_param)

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
    
    @action(detail=False, methods=['get'], url_path='meta')
    def get_events_meta(self, request):
        event_types = [t for t, _ in Event.EventType.choices]
        return Response({
            'event_types': event_types,
        })
    @action(detail=False, methods=['get'], url_path='breakdowns-meta')
    def get_breakdowns_meta(self, request):
        sexs = [sex for sex, _ in DemographicCount.Sex.choices]
        sex_labels = [choice.label for choice in DemographicCount.Sex]
        age_ranges = [ar for ar, _ in DemographicCount.AgeRange.choices]
        age_range_labels = [choice.label for choice in DemographicCount.AgeRange]
        kp_types = [kp for kp, _ in DemographicCount.KeyPopulationType.choices]
        kp_type_labels = [choice.label for choice in DemographicCount.KeyPopulationType]
        dis_types = [dis for dis, _ in DemographicCount.DisabilityType.choices]
        dis_labels = [dis.label for dis in DemographicCount.DisabilityType]
        statuses = [s for s, _ in DemographicCount.Status.choices]
        status_labels = [s.label for s in DemographicCount.Status]
        citizenships = [c for c, _ in DemographicCount.Citizenship.choices]
        citizenship_labels = [c.label for c in DemographicCount.Citizenship]
        return Response({
            'status': statuses,
            'status_labels': status_labels,
            'sex': sexs,
            'sex_labels': sex_labels,
            'age_range': age_ranges,
            'age_range_labels': age_range_labels,
            'kp_type': kp_types,
            'kp_type_labels': kp_type_labels,
            'disability_type': dis_types,
            'disability_type_labels': dis_labels,
            'citizenship': citizenships,
            'citizenship_labels': citizenship_labels,
        })
    
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
            if EventTask.objects.filter(event=event, task__organization__id=organization_id).exists():
                return Response(
                        {"detail": "You cannot remove an organization from a project when they have a task in the organization."},
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
            existing_task_prereq = [t.task.indicator.prerequisite.id for t in EventTask.objects.filter(event=event) if t.task.indicator.prerequisite]
            if task_link.task.indicator.id in existing_task_prereq:
                return Response(
                        {"detail": "You cannot remove a task from an event when it is a prerequisite for another task in this event."},
                        status=status.HTTP_409_CONFLICT
                    )
            if DemographicCount.objects.filter(event=event, task=task_link.task).exists():
                 return Response(
                        {"detail": "You cannot remove a task from an event when it is associated with an existing count."},
                        status=status.HTTP_409_CONFLICT
                    )
            task_link.delete()
            return Response({"detail": f"Task removed from event."}, status=status.HTTP_200_OK)

        except EventOrganization.DoesNotExist:
            return Response({"detail": "Task not associated with this event."}, status=status.HTTP_404_NOT_FOUND)
    @action(detail=True, methods=['get'], url_path='get-counts')
    def get_counts(self, request, pk=None):
        event=self.get_object()
        user=request.user

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
        queryset = DemographicCount.objects.filter(event=event)
        serializer = DCSerializer(queryset, many=True)
        return Response(serializer.data)
    
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
           if not event.host or not (
                user.organization == event.host or
                user.organization == event.host.parent_organization or
                EventOrganization.objects.filter(organization = user.organization).exists() 
            ):
                return Response(
                {'detail': 'You do not have permission to edit counts for this event.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if event.event_date > date.today():
            return Response(
                {'detail': 'You cannot add counts for events in the future.'},
                status=status.HTTP_400_BAD_REQUEST
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

        to_create = []

        grouped_counts = defaultdict(list)
        for count in counts:
            task_id = count.get('task_id')
            if not task_id:
                return Response({'detail': 'Each count must include a task_id.'}, status=400)
            grouped_counts[task_id].append(count)

        for task_id, group in grouped_counts.items():
            task = tasks.get(task_id)
            if not task or task.id not in event_task_ids:
                return Response({'detail': f'Invalid or unauthorized Task: {task_id}'}, status=400)
            elif user.role !='admin':
                if not (task.organization == user.organization or task.organization.parent_organization == user.organization):
                    return Response(
                        {'detail': 'You do not have permission to edit counts for this task.'},
                        status=status.HTTP_403_FORBIDDEN
                    )

            # Delete existing counts for this task in this event
            DemographicCount.objects.filter(event=event, task=task).delete()

            seen_keys = set()
            for count in group:
                flagged = False
                amount = count.get('count')
                if not amount or amount in ['', None]:
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

                org_id = count.get('organization_id')
                org = None
                if org_id:
                    org = orgs.get(org_id)
                    if not org or org.id not in event_org_ids:
                        return Response({'detail': f'Invalid Organization: {org_id}'}, status=400)
                    
    

                if task.indicator.subcategories.exists():
                    subcategory_id = count.get('subcategory_id')
                    if not subcategory_id:
                        return Response({'detail': f'Task {task.indicator.name} requires a subcategory.'}, status=400)
                    subcategory = subcategories.get(subcategory_id)
                    if not subcategory or subcategory not in task.indicator.subcategories.all():
                        return Response({'detail': f'Subcategory id {subcategory_id} is not valid for task {task.indicator.name}'}, status=400)
                else:
                    subcategory = None
                
                if task.indicator.prerequisite:
                    prereq = task.indicator.prerequisite
                    prerequisite_count = DemographicCount.objects.filter(
                        event=event, task__indicator = prereq, sex=sex, age_range=age_range, citizenship=citizenship,
                        hiv_status=hiv_status, pregnancy=pregnancy, disability_type=disability_type,
                        kp_type=kp_type, subcategory=subcategory, organization=org,
                        status=status_name).first()
                    if not prerequisite_count or prerequisite_count.count < amount:
                        flagged = True
                
                key = (
                    sex, age_range, citizenship, hiv_status, pregnancy, disability_type,
                    kp_type, status_name, subcategory.id if subcategory else None,
                    org.id if org else None
                )
                if key in seen_keys:
                    return Response({'detail': f'Duplicate count breakdown for task {task_id}'}, status=400)
                seen_keys.add(key)

                instance = DemographicCount(
                    event=event, count=amount, sex=sex, age_range=age_range, citizenship=citizenship,
                    hiv_status=hiv_status, pregnancy=pregnancy, disability_type=disability_type,
                    kp_type=kp_type, task=task, subcategory=subcategory, organization=org,
                    status=status_name, created_by=user, flagged=flagged
                )
                to_create.append(instance)

        DemographicCount.objects.bulk_create(to_create)

        return Response({
            'created': DCSerializer(to_create, many=True).data,
        }, status=200)
    
    @action(detail=True, methods=['patch'], url_path='flag-counts/(?P<task_id>[^/.]+)')
    def flag_count(self, request, pk=None, task_id=None):
        event=self.get_object()
        user=request.user
        set_flag = request.data.get('set_flag', None)
        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {'detail': 'You do not have permission to flag event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if user.role != 'admin':
            if not event.host or event.host != user.organization or event.host.parent_organization != user.organization:
                return Response(
                    {'detail': 'You do not have permission to flag counts for this event.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        if set_flag is None:
            return Response(
                {'detail': 'Missing flag status.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        set_flag = str(set_flag).lower() in ['true', '1']

        counts = DemographicCount.objects.filter(event=event, task__id=task_id)
        for count in counts: 
            print(set_flag)
            count.flagged = set_flag 
            count.save()
        return Response({"detail": f"Count flagged."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'], url_path='delete-count/(?P<task_id>[^/.]+)')
    def delete_count(self, request, pk=None, task_id=None):
        event=self.get_object()
        user=request.user

        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {'detail': 'You do not have permission to remove event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if user.role != 'admin':
            if not event.host or event.host != user.organization or event.host.parent_organization != user.organization:
                return Response(
                    {'detail': 'You do not have permission to remove counts for this event.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        counts = DemographicCount.objects.filter(event=event, task__id=task_id)
        for count in counts: 
            count.delete() 
        return Response({"detail": f"Count deleted."}, status=status.HTTP_200_OK)
        
            