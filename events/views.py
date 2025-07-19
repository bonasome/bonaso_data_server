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
from events.models import Event, DemographicCount, EventTask, EventOrganization, CountFlag
from organizations.models import Organization
from projects.models import Project, Task
from indicators.models import Indicator, IndicatorSubcategory
from events.serializers import EventSerializer, DCSerializer
from django.contrib.auth import get_user_model
from collections import defaultdict
from datetime import date
from django.utils.timezone import now

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
        event_statuses = [s for s, _ in Event.EventStatus.choices]
        event_status_labels = [choice.label for choice in Event.EventStatus]
        return Response({
            'event_types': event_types,
            'statuses': event_statuses,
            'status_labels': event_status_labels
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
        hiv_statuses = [c for c, _ in DemographicCount.HIVStatus.choices]
        hiv_status_labels = [c.label for c in DemographicCount.HIVStatus]
        pregnant = [c for c, _ in DemographicCount.Pregnancy.choices]
        pregnant_labels = [c.label for c in DemographicCount.Pregnancy]
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
            'hiv_status': hiv_statuses,
            'hiv_status_labels': hiv_status_labels,
            'pregnancy': pregnant,
            'pregnancy_labels': pregnant_labels,
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
        from events.utils import get_breakdown_keys, get_schema_key, make_key
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
        valid_hiv = [c for c, _ in DemographicCount.HIVStatus.choices]
        valid_preg = [c for c, _ in DemographicCount.Pregnancy.choices]


        to_create = []
        to_update = []

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

            existing_counts = list(DemographicCount.objects.filter(task=task).values())

            existing_schema = get_schema_key(existing_counts)
            incoming_schema = get_schema_key(group)

            update = False
            existing_map = {}
            if existing_schema != incoming_schema:
                schema_keys = list(incoming_schema)
                DemographicCount.objects.filter(event=event, task=task).delete()
            else:
                update=True
                schema_keys = list(existing_schema)
                existing_map = {
                    make_key(c, schema_keys): c['count'] for c in existing_counts
                }

            seen_keys = set()
            for count in group:
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
                if hiv_status and hiv_status not in valid_hiv:
                    return Response({'detail': f'Invalid HIV Status: {hiv_status}'}, status=400)
                
                pregnancy = count.get('pregnancy')
                if pregnancy and pregnancy not in valid_preg:
                    return Response({'detail': f'Invalid Pregnancy Status: {pregnancy}'}, status=400)

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
                
                key = make_key(count, schema_keys)
                if key in seen_keys:
                    return Response({'detail': f'Duplicate count breakdown for task {task_id}'}, status=400)
                seen_keys.add(key)
                
                if update and key in existing_map:
                    if amount != existing_map[key]:
                        existing_count = DemographicCount.objects.filter(task=task, **dict(key)).first()
                        existing_count.count = amount
                        to_update.append(existing_count)
                    continue

                instance = DemographicCount(
                    event=event, count=amount, sex=sex, age_range=age_range, citizenship=citizenship,
                    hiv_status=hiv_status, pregnancy=pregnancy, disability_type=disability_type,
                    kp_type=kp_type, task=task, subcategory=subcategory, organization=org,
                    status=status_name, created_by=user
                )
                to_create.append(instance)
                
        DemographicCount.objects.bulk_create(to_create)
        DemographicCount.objects.bulk_update(to_update, ['count'])
        

        all_edited = to_create+to_update
        grouped_obj = defaultdict(list)
        for count in all_edited:
            task_id = count.task.id
            grouped_obj[task_id].append(count)
        
        to_flag = []
        to_resolve = []
        for task_id, group in grouped_obj.items():
            existing_flags = CountFlag.objects.filter(count__event=event, count__task__id=task_id)
        
            for instance in group:
                task = instance.task
                if task.indicator.prerequisites:
                    for prereq in task.indicator.prerequisites.all():
                        prerequisite_count = DemographicCount.objects.filter(
                            event=instance.event,
                            task__indicator=prereq,
                            sex=instance.sex,
                            age_range=instance.age_range,
                            citizenship=instance.citizenship,
                            hiv_status=instance.hiv_status,
                            pregnancy=instance.pregnancy,
                            disability_type=instance.disability_type,
                            kp_type=instance.kp_type,
                            subcategory=instance.subcategory,
                            organization=instance.organization,
                            status=instance.status
                        ).first()

                        reason = f'Task "{task.indicator.name}" has a prerequisite "{prereq.name}" that does not have an associated count.'
                        if not prerequisite_count:
                            already_flagged = existing_flags.filter(count=instance, reason=reason).exists()
                            if not already_flagged:
                                to_flag.append(CountFlag(
                                    count=instance,
                                    reason=reason,
                                    auto_flagged=True
                                ))
                        else:
                            outstanding_flag = existing_flags.filter(count=instance, reason=reason, resolved=False).first()
                            if outstanding_flag:

                                outstanding_flag.resolved=True
                                outstanding_flag.auto_resolved=True
                                outstanding_flag.resolved_at=now()
                                to_resolve.append(outstanding_flag)

                        reason=f'The amount of this count is greater than its corresponding prerequisite "{prereq.name}" amount.'
                        if prerequisite_count and prerequisite_count.count < instance.count:
                            to_flag.append(CountFlag(
                                count=instance,
                                reason=reason,
                                auto_flagged=True
                            ))
                        else:
                            outstanding_flag = existing_flags.filter(count=instance, reason=reason, resolved=False).first()
                            if outstanding_flag:
                                outstanding_flag.resolved=True
                                outstanding_flag.auto_resolved=True
                                outstanding_flag.resolved_at=now()
                                to_resolve.append(outstanding_flag)

        CountFlag.objects.bulk_create(to_flag)
        CountFlag.objects.bulk_update(to_resolve, ['resolved', 'auto_resolved', 'resolved_at'])
        return Response({
            'created': DCSerializer(to_create, many=True).data,
        }, status=200)

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

    @action(detail=True, methods=['patch'], url_path='flag-counts/(?P<task_id>[^/.]+)')
    def flag_all_counts(self, request, pk=None, task_id=None):
        event=self.get_object()
        user=request.user
        reason = request.data.get('reason', None)
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
        if reason is None:
            return Response(
                {'detail': 'Missing flag reason.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        counts = DemographicCount.objects.filter(event=event, task__id=task_id)
        to_create = []
        for count in counts: 
            instance = CountFlag(count=count, created_by=user, reason=reason)
            to_create.append(instance)
        CountFlag.objects.bulk_create(to_create)
        return Response({"detail": f"Flagged {len(to_create)} counts."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['patch'], url_path='resolve-count-flags/(?P<task_id>[^/.]+)')
    def resolve_all_counts(self, request, pk=None, task_id=None):
        event=self.get_object()
        user=request.user
        reason = request.data.get('resolved_reason', None)
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
        if reason is None:
            return Response(
                {'detail': 'Missing resolved status.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        flags = CountFlag.objects.filter(count__event=event, count__task__id=task_id)
        print(flags.count())
        for flag in flags: 
            flag.resolved = True
            flag.resolved_at = now()
            flag.resolved_by = user
            flag.reason_resolved = reason
            flag.save()
        return Response({"detail": f"Resolved {flags.count()} flags."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='flag-count/(?P<count_id>[^/.]+)')
    def flag_count(self, request, pk=None, count_id=None):
        from events.serializers import CountFlagSerializer
        event=self.get_object()
        user=request.user
        reason = request.data.get('reason', None)
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
        if reason is None:
            return Response(
                {'detail': 'Missing flag reason.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        count = DemographicCount.objects.filter(id=count_id).first()
        if not count:
            return Response(
                {'detail': 'Invalid count id provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        flag = CountFlag.objects.create(count=count, created_by=user, reason=reason)
        serializer = CountFlagSerializer(flag)
        return Response({"detail": f"Flagged count {count_id}.", "flag": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='resolve-flag/(?P<count_flags_id>[^/.]+)')
    def resolve_count(self, request, pk=None, count_flags_id=None):
        from events.serializers import CountFlagSerializer
        event=self.get_object()
        user=request.user
        reason = request.data.get('resolved_reason', None)
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
        if reason is None:
            return Response(
                {'detail': 'Missing flag reason.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        flag = CountFlag.objects.filter(id=count_flags_id).first()
        if not flag:
            return Response(
                {'detail': 'Flag does not exist.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        flag.resolved = True
        flag.resolved_at = now()
        flag.resolved_by = user
        flag.resolved_reason = reason
        flag.save()
        serializer = CountFlagSerializer(flag)
        return Response({"detail": f"Resolved flag.", "flag": serializer.data}, status=status.HTTP_200_OK)
        
            