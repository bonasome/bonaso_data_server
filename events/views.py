from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Q
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
from events.utils import get_schema_key, make_key, count_flag_logic
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
            queryset = Event.objects.filter(tasks__project__client=user.client_organization)
            queryset=queryset.distinct()
        #higher roles can see event where they are the host, their child is the host, or they are a participant
        elif user.role in ['meofficer', 'manager']:
           queryset = Event.objects.filter(
                Q(host=user.organization) |
                Q(organizations=user.organization) |
                Q(host__in=ProjectOrganization.objects.filter(
                    parent_organization=user.organization
                ).values_list('organization', flat=True))
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
    
    @action(detail=False, methods=['get'], url_path='breakdowns-meta')
    def get_breakdowns_meta(self, request):
        '''
        Action that pulls a list of values/labels for use when creating counts in the front end. 
        '''
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
        '''
        Only admins can delete events and events that have counts attached should be protected.
        '''
        user = request.user
        instance = self.get_object()
        # Only admins can delete
        if user.role != 'admin':
            return Response(
                {"detail": "You cannot delete a project."},
                status=status.HTTP_403_FORBIDDEN 
            )
        # Prevent deletion of events that have counts
        if DemographicCount.objects.filter(event = instance).exists():
            return Response(
                {"detail": ("This event already has data associated with it, and cannot be deleted.")},
                status=status.HTTP_409_CONFLICT
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='get-counts')
    def get_counts(self, request, pk=None):
        '''
        Retreive all counts associated with a given event.
        '''
        event=self.get_object()
        user=request.user
        
        #queryset level checks and the below queryset should filter most of this, but just to e safe
        if user.role not in ['meofficer', 'admin', 'manager', 'client']:
            return Response(
                {'detail': 'You do not have permission to view event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        #filter counts to only the event
        queryset = DemographicCount.objects.filter(event=event)

        #admin/client should have access to everything if this event is in the viewset queryset
        if user.role not in ['client', 'admin']:
            #else limit to only seeing their org/child orgs
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            queryset.filter(Q(task__organization=user.organization) | Q(task__organization__in=child_orgs))
            
        serializer = DCSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @transaction.atomic
    @action(detail=True, methods=['patch'], url_path='update-counts')
    def update_counts(self, request, pk=None):
        '''
        Since there are a lot of rules around creating counts and this process is pretty complex, we handle creating
        and updating counts in a dedicated action rather than a serializer. The intent is users will edit
        counts in a tabular format that is uploaded in one batch. 

        Endpoint expects counts as an array, with each array containing a dict that has all the information.
        example : {
            count: 20 (int),
            sex: F (string/enum)
            ...
        } 
        '''
        event=self.get_object()
        user = request.user
        counts = request.data.get('counts', [])
        
        ###===PERMISSION CHECKS===###
        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {'detail': 'You do not have permission to edit event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        ###===Prevent adding counts for events that haven't started yet===###
        if event.start > date.today():
            return Response(
                {'detail': 'You cannot add counts for events in the future.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        #Take ids and convert them to objects
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

        #get a list of valid demographic breakdown values
        valid_sexs = [sex for sex, _ in DemographicCount.Sex.choices]
        valid_age_ranges = [ar for ar, _ in DemographicCount.AgeRange.choices]
        valid_kp_types = [kp for kp, _ in DemographicCount.KeyPopulationType.choices]
        valid_disability_types = [dis for dis, _ in DemographicCount.DisabilityType.choices]
        valid_statuses = [s for s, _ in DemographicCount.Status.choices]
        valid_citizenships = [c for c, _ in DemographicCount.Citizenship.choices]
        valid_hiv = [c for c, _ in DemographicCount.HIVStatus.choices]
        valid_preg = [c for c, _ in DemographicCount.Pregnancy.choices]

        '''
        create seperate lists for new counts or updated counts
        if a count has the same breakdowns/same task as a previous task, its considered an update
            ex: male, 20-24 = 4 --> male, 20-24 = 6 --> update 
            male, 20-24 = 4 --> male = 4 --> create (breakdowns are different)
        This helps manage flags between edits
        '''
        to_create = []
        to_update = []

        #group counts by task (usually only one of these is sent at a time)
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
                #make sure that non admins can only create counts for tasks they have perms for
                if not (task.organization == user.organization or ProjectOrganization.objects.filter(organization=task.organization, parent_organization=user.organization, project=task.project).exists()):
                    return Response(
                        {'detail': 'You do not have permission to edit counts for this task.'},
                        status=status.HTTP_403_FORBIDDEN
                    )

            #map count schema
            existing_counts = list(DemographicCount.objects.filter(task=task).values())

            existing_schema = get_schema_key(existing_counts)
            incoming_schema = get_schema_key(group)

            #check if the schema already exists
            update = False
            existing_map = {}
            if existing_schema != incoming_schema:
                #if there is no matching schema, delete any other counts with this task to prevent bloat (if breakdowns are changed)
                schema_keys = list(incoming_schema)
                DemographicCount.objects.filter(event=event, task=task).delete()
            else:
                update=True
                schema_keys = list(existing_schema)
                existing_map = {
                    make_key(c, schema_keys): c['count'] for c in existing_counts
                }

            #track keys to prevent duplicates (i.e., there should not be two seperate counts for male, 20-24)
            seen_keys = set()

            #loop through each count to verify the details
            for count in group:
                amount = count.get('count')
                #if count is none don't bother
                if not amount or amount in ['', None]:
                    continue
                
                #confirm its an int
                if not str(amount).strip().isdigit():
                    return Response({'detail': f'Provided Amount {amount} is invalid'}, status=400)
                amount = int(amount)
                
                #verify that the each choice field is valid
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

                #by default, a task with subcats requires the correct subcat information to be sent
                if task.indicator.subcategories.exists():
                    subcategory_id = count.get('subcategory_id')
                    if not subcategory_id:
                        return Response({'detail': f'Task {task.indicator.name} requires a subcategory.'}, status=400)
                    subcategory = subcategories.get(subcategory_id)
                    if not subcategory or subcategory not in task.indicator.subcategories.all():
                        return Response({'detail': f'Subcategory id {subcategory_id} is not valid for task {task.indicator.name}'}, status=400)
                else:
                    subcategory = None
                
                #create a new breakdown key
                key = make_key(count, schema_keys)
                if key in seen_keys:
                    return Response({'detail': f'Duplicate count breakdown for task {task_id}'}, status=400)
                seen_keys.add(key)
                
                # if its an update, just edit the count with the matching key
                if update and key in existing_map:
                    if amount != existing_map[key]:
                        existing_count = DemographicCount.objects.filter(task=task, **dict(key)).first()
                        existing_count.count = amount
                        to_update.append(existing_count)
                    continue
                # else create the demofaphic count
                instance = DemographicCount(
                    event=event, count=amount, sex=sex, age_range=age_range, citizenship=citizenship,
                    hiv_status=hiv_status, pregnancy=pregnancy, disability_type=disability_type,
                    kp_type=kp_type, task=task, subcategory=subcategory, organization=org,
                    status=status_name, created_by=user
                )
                to_create.append(instance)
        #bulk create/update  
        DemographicCount.objects.bulk_create(to_create)
        DemographicCount.objects.bulk_update(to_update, ['count'])
        
        #get all counts together
        all_edited = to_create+to_update
        grouped_obj = defaultdict(list)
        for count in all_edited:
            task_id = count.task.id
            grouped_obj[task_id].append(count)
        
        for task_id, group in grouped_obj.items():
            for instance in group:
                count_flag_logic(instance, user)
                downstream_counts = DemographicCount.objects.filter(event=event, task__indicator__prerequisites=instance.task.indicator)
                for downstream_count in downstream_counts:
                    count_flag_logic(downstream_count, user)

        return Response({
            'edited': DCSerializer(all_edited, many=True).data,
        }, status=200)

    @action(detail=True, methods=['delete'], url_path='delete-count/(?P<task_id>[^/.]+)')
    def delete_count(self, request, pk=None, task_id=None):
        '''
        Hosts/admins can delete counts.
        '''
        event=self.get_object()
        user=request.user

        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {'detail': 'You do not have permission to remove event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        if user.role != 'admin':
            if event.host!= user.organization:
                return Response(
                    {'detail': 'You do not have permission to remove counts for this event.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        counts = DemographicCount.objects.filter(event=event, task__id=task_id)
        for count in counts: 
            count.delete() 
        return Response({"detail": f"Count deleted."}, status=status.HTTP_200_OK)