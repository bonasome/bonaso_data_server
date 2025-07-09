from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from events.models import Event, DemographicCount, EventTask, EventOrganization
from projects.models import Project, Task
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer, OrganizationSerializer
from projects.serializers import TaskSerializer


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
                  'task_id', 'location', 'event_date', 'event_type']
    
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
        existing_task_ids = set(
            EventTask.objects.filter(event=event).values_list('task_id', flat=True)
        )
        new_links = []
        for task in tasks:
            start = task.project.start
            end = task.project.end
            if not start <= event.event_date <= end:
                raise serializers.ValidationError(
                    f"Task '{task.indicator.name}' for organization '{task.organization.name}' is associcated with a project whose start and end dates do not align with this events date."
                )
            if user.role != 'admin':
                if not task.organization == user.organization and not task.organization.parent_organization == user.organization:
                    raise PermissionDenied(
                        f"Cannot assign a task that is not associcated with your organization or child organization."
                    )
            if task.id not in existing_task_ids:
                new_links.append(EventTask(event=event, task=task, added_by=user))

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

        organizations = validated_data.pop('organizations', [])
        tasks = validated_data.pop('tasks', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Add new organizations (append-only)
        self._add_organizations(instance, organizations, user)
        self._add_tasks(instance, tasks, user)
        return instance