from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from events.models import Event, DemographicCount, EventTask, EventOrganization, CountFlag
from projects.models import Project, Task
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer, OrganizationSerializer
from projects.serializers import TaskSerializer
from datetime import date

class CountFlagSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    resolved_by = serializers.SerializerMethodField()
    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "first_name": obj.created_by.first_name,
                "last_name": obj.created_by.last_name,
            }
        return None
    def get_resolved_by(self, obj):
        if obj.resolved_by:
            return {
                "id": obj.resolved_by.id,
                "username": obj.resolved_by.username,
                "first_name": obj.resolved_by.first_name,
                "last_name": obj.resolved_by.last_name,
            }
        return None
    
    class Meta:
        model=CountFlag
        fields = [
            'id', 'reason', 'auto_flagged', 'created_by', 'created_at', 'resolved', 'auto_resolved',
            'resolved_reason', 'resolved_by', 'resolved_at'
        ]

class DCSerializer(serializers.ModelSerializer):
    organization=OrganizationListSerializer(read_only=True)
    task = TaskSerializer(read_only=True)
    count_flags = CountFlagSerializer(read_only=True, many=True)
    class Meta:
        model=DemographicCount
        fields = '__all__'
        
class EventSerializer(serializers.ModelSerializer):
    host = OrganizationListSerializer(read_only=True)
    host_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, required=False, allow_null=True, source='host')
    organizations = OrganizationListSerializer(many=True, read_only=True)
    tasks = TaskSerializer(many=True, read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), required=False, many=True, write_only=True, source='organizations')
    task_id = serializers.PrimaryKeyRelatedField(queryset= Task.objects.all(), many=True, required=False, write_only=True, source='tasks')

    class Meta:
        model = Event
        fields = ['id', 'name', 'description', 'host', 'host_id', 'tasks', 'organizations', 'organization_id', 
                  'task_id', 'location', 'event_date', 'event_type', 'status']
    
    def _add_organizations(self, event, organizations, user):
        existing_org_ids = set(
            EventOrganization.objects.filter(event=event).values_list('organization_id', flat=True)
        )
        new_links = []
        for org in organizations:
            if user.role != 'admin':
                if not org == user.organization and not org.parent_organization == user.organization:
                    raise PermissionDenied(
                        f"Cannot assign an organization that is not your organization or your child organization."
                    )
            if org.id not in existing_org_ids:
                new_links.append(EventOrganization(event=event, organization=org, added_by=user))
        EventOrganization.objects.bulk_create(new_links)

    def _add_tasks(self, event, tasks, user):
        existing_task_ids = [t.task.id for t in EventTask.objects.filter(event=event)]
        new_indicators = [t.indicator.id for t in tasks]
        old_indicators = [t.task.indicator.id for t in EventTask.objects.filter(event=event)]
        new_links = []
        for task in tasks:
            if user.role != 'admin':
                if not task.organization == user.organization and not task.organization.parent_organization == user.organization:
                    raise PermissionDenied(
                        f"Cannot assign a task that is not associcated with your organization or child organization."
                    )
            org = task.organization
            if not EventOrganization.objects.filter(organization=org).exists() and not event.host==org:
                raise serializers.ValidationError(
                    f"Task '{task.indicator.name}' is associated with '{task.organization.name}' who is not associated with this event. Please add them first."
                )
            start = task.project.start
            end = task.project.end
            if not start <= event.event_date <= end:
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

    @transaction.atomic
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])
        tasks = validated_data.pop('tasks', [])
        event = Event.objects.create(**validated_data)

        self._add_organizations(event, organizations, user)
        self._add_tasks(event, tasks, user)
        return event


    @transaction.atomic
    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        event_date = validated_data.pop('event_date', instance.event_date)
        if event_date > date.today() and DemographicCount.objects.filter(event=instance).exists():
            raise serializers.ValidationError(
                "You cannot set an event for the future if it already has counts associated with it."
            )
        organizations = validated_data.pop('organizations', [])
        tasks = validated_data.pop('tasks', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Add new organizations (append-only)
        self._add_organizations(instance, organizations, user)
        self._add_tasks(instance, tasks, user)
        return instance