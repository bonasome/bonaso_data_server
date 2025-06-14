from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from projects.models import Project, Task, Client, Target
from organizations.models import Organization
from indicators.models import Indicator
from organizations.serializers import OrganizationListSerializer
from indicators.serializers import IndicatorSerializer
from users.models import User

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model=Client
        fields=['id', 'name']

class TaskSerializer(serializers.ModelSerializer):
    organization = OrganizationListSerializer(read_only=True)
    indicator = IndicatorSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True)
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), write_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True)
    parent_task = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(),
        required=False,   # optional
        allow_null=True
    )
    class Meta:
        model=Task
        fields = ['id', 'indicator', 'organization', 'project', 'indicator_id', 'project_id', 'organization_id', 'parent_task']

class ProjectListSerializer(serializers.ModelSerializer):
    client = ClientSerializer(read_only=True)
    class Meta:
        model = Project
        fields = ['id', 'name', 'client', 'start', 'end', 'status']

class ProjectDetailSerializer(serializers.ModelSerializer):
    tasks = TaskSerializer(many=True, read_only=True)
    client = ClientSerializer(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), write_only=True, source='client')
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), many=True, write_only=True, source='organizations')
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), many=True, write_only=True, source='indicators')
    organizations = OrganizationListSerializer(read_only=True, many=True)
    indicators = IndicatorSerializer(read_only=True, many=True)
    class Meta:
        model=Project
        fields = ['id', 'name','client', 'start', 'end', 'description', 'tasks', 'client_id',
                  'organization_id', 'indicator_id', 'organizations', 'indicators', 'status']

    def validate(self, attrs):
        start = attrs.get('start', getattr(self.instance, 'start', None))
        end = attrs.get('end', getattr(self.instance, 'end', None))

        if start and end and end < start:
            raise serializers.ValidationError("Start date must be before end date")
        return attrs

    def create(self, validated_data):
        organizations = validated_data.pop('organizations', [])
        inds = validated_data.pop('indicators', [])
        project = Project.objects.create(**validated_data)

        project.organizations.set(organizations)
        project.indicators.set(inds)
        return project
    
    def update(self, instance, validated_data):
        organizations = validated_data.pop('organizations', [])
        indicators = validated_data.pop('indicators', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if organizations is not None:
            instance.organizations.set(organizations)
        if indicators is not None:
            instance.indicators.set(indicators)

        return instance


class TargetSerializer(serializers.ModelSerializer):
    task = TaskSerializer(read_only=True)
    task_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, source='task')
    related_to = TaskSerializer(read_only=True)
    related_to_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, required=False, source='related_to')
    class Meta:
        model = Target
        fields = ['id', 'task', 'task_id', 'start', 'end', 'amount','related_to', 'related_to_id', 'percentage_of_related',  ]
    
    def validate(self, attrs):
        task = attrs.get('task')
        related = attrs.get('related_to')
        if not task:
            raise serializers.ValidationError({'task_id': 'Task not found.'})

        if related and related.project != task.project:
            raise serializers.ValidationError({'related_to_id': 'Related target must belong to the same project.'})

        if related and related.organization != task.organization:
            raise serializers.ValidationError({'related_to_id': 'Related target must be assigned to the same organization.'})
        
        if not attrs.get('amount') and (not related or not attrs.get('percentage_of_related')):
            raise serializers.ValidationError("Either 'amount' or both 'related_to' and 'percentage_of_related' must be provided.")
        
        
        start = attrs.get('start', getattr(self.instance, 'start', None))
        end = attrs.get('end', getattr(self.instance, 'end', None))
        if start and end and end < start:
            raise serializers.ValidationError("Start date must be before end date")

        if task and start and end:
            overlaps = Target.objects.filter(
                task=task,
                start__lte=end,
                end__gte=start,
            )
            if self.instance:
                overlaps = overlaps.exclude(pk=self.instance.pk)

            if overlaps.exists():
                raise serializers.ValidationError("This target overlaps with an existing target.")
        
        return attrs

