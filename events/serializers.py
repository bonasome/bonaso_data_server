from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from django.db import transaction
from datetime import date

from events.models import Event, DemographicCount, EventTask, EventOrganization
from profiles.serializers import ProfileListSerializer
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from projects.models import ProjectOrganization,Task
from projects.serializers import TaskSerializer
from flags.serializers import FlagSerializer



class DCSerializer(serializers.ModelSerializer):
    '''
    Used to view counts. Since counts are a bit complex, we handle update/creation in a dedicated action in the
    viewset.
    '''
    flags = FlagSerializer(read_only=True, many=True)
    organization=OrganizationListSerializer(read_only=True)
    task = TaskSerializer(read_only=True)
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    class Meta:
        model=DemographicCount
        fields = '__all__'
        
class EventSerializer(serializers.ModelSerializer):
    '''
    Used for creating/editing event details, including managing tasks/orgs. Also links to counts serializer.
    '''

    host = OrganizationListSerializer(read_only=True)
    host_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, required=False, allow_null=True, source='host')
    organizations = OrganizationListSerializer(many=True, read_only=True)
    tasks = TaskSerializer(many=True, read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), required=False, many=True, write_only=True, source='organizations')
    task_id = serializers.PrimaryKeyRelatedField(queryset= Task.objects.all(), many=True, required=False, write_only=True, source='tasks')
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)

    class Meta:
        model = Event
        fields = [
                    'id', 'name', 'description', 'host', 'host_id', 'tasks', 'organizations', 'organization_id', 
                    'task_id', 'location', 'start', 'end', 'event_type', 'status', 'created_by', 'created_at',
                    'updated_by', 'updated_at'
                ]
    
    def _add_organizations(self, event, organizations, user):
        '''
        Add an org, assuming that org perms are met.
        '''
        existing_org_ids = set(
            EventOrganization.objects.filter(event=event).values_list('organization_id', flat=True)
        )
        new_links = []
        for org in organizations:
            if user.role != 'admin':
                if not org == user.organization and not ProjectOrganization.objects.filter(organization=org, parent_organization=user.organization).exists():
                    raise PermissionDenied(
                        f"Cannot assign an organization that is not your organization or your child organization."
                    )
            if org.id not in existing_org_ids:
                new_links.append(EventOrganization(event=event, organization=org, added_by=user))
        EventOrganization.objects.bulk_create(new_links)

    def _add_tasks(self, event, tasks, user):
        '''
        Add a task assuming org perms/project dates line up.
        '''
        existing_task_ids = [t.task.id for t in EventTask.objects.filter(event=event)]
        new_links = []
        for task in tasks:
            org = task.organization
            if user.role != 'admin':
                 if not org == user.organization and not ProjectOrganization.objects.filter(organization=org, parent_organization=user.organization, project=task.project).exists():
                    raise PermissionDenied(
                        f"Cannot assign a task that is not associcated with your organization or child organization."
                    )
            if not EventOrganization.objects.filter(organization=org).exists() and not event.host==org:
                raise serializers.ValidationError(
                    f"Task '{task.indicator.name}' is associated with '{task.organization.name}' who is not associated with this event. Please add them first."
                )
            if event.start < task.project.start or event.end > task.project.end:
                raise serializers.ValidationError(
                    f"Task '{task.indicator.name}' for organization '{task.organization.name}' is associcated with a project whose start and end dates do not align with this events date."
                )
            if task.id not in existing_task_ids:
                new_links.append(EventTask(event=event, task=task, added_by=user))
            else:
                raise serializers.ValidationError(
                    f"Task '{task.indicator.name} is already in this project"
                )

        EventTask.objects.bulk_create(new_links)

    def validate(self, attrs):
        user = self.context.get('request').user if self.context.get('request') else None
        if user.role not in ['admin', 'meofficer', 'manager']:
            raise PermissionDenied('You do not have permission to edit events.')
        host = attrs.get('host', getattr(self.instance, 'host', None))
        if not host:
            raise serializers.ValidationError(
                    f"Event host is required."
                )
        if user.role != 'admin':
            is_own_org = host == user.organization
            is_child_org = ProjectOrganization.objects.filter(
                    parent_organization=user.organization,
                    organization=host
                ).exists()

            if not (is_own_org or is_child_org):
                raise PermissionDenied("You do not have permission to edit events not related to your organization.")
        
        start = attrs.get('start', getattr(self.instance, 'start', None))
        end = attrs.get('end', getattr(self.instance, 'end', None))
        if start and end and end < start:
            raise serializers.ValidationError("Event end may not be before event start.")
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])
        tasks = validated_data.pop('tasks', [])
        event = Event.objects.create(**validated_data)

        self._add_organizations(event, organizations, user)
        self._add_tasks(event, tasks, user)
        event.created_by = user
        event.save()
        return event


    @transaction.atomic
    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        start = validated_data.get('start', instance.start)
        #validation to make sure that changing event dates doesn't create confusion with counts already existing
        if start > date.today() and DemographicCount.objects.filter(event=instance).exists():
            raise serializers.ValidationError(
                "You cannot set an event for the future if it already has counts associated with it."
            )
        organizations = validated_data.pop('organizations', [])
        tasks = validated_data.pop('tasks', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()

        # Add new organizations (append-only)
        self._add_organizations(instance, organizations, user)
        self._add_tasks(instance, tasks, user)
        return instance