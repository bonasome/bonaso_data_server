from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q

from projects.models import Project, Task, Client, Target, ProjectIndicator, ProjectOrganization
from organizations.models import Organization
from indicators.models import Indicator
from organizations.serializers import OrganizationListSerializer
from indicators.serializers import IndicatorSerializer
from users.models import User

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model=Client
        fields=['id', 'name']



class ProjectListSerializer(serializers.ModelSerializer):
    client = ClientSerializer(read_only=True)
    class Meta:
        model = Project
        fields = ['id', 'name', 'client', 'start', 'end', 'status']

class TaskSerializer(serializers.ModelSerializer):
    indicator = IndicatorSerializer(read_only=True)
    project = ProjectListSerializer(read_only=True)
    organization = OrganizationListSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True)
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), write_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True)
    parent_task = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(),
        required=False,   # optional
        allow_null=True
    )
    targets = serializers.SerializerMethodField()

    def get_targets(self, obj):
        request = self.context.get('request')
        if request and request.query_params.get('include_targets') == 'true':
            return TargetForTaskSerializer(obj.target_set.all(), many=True, context=self.context).data
        return None
    
    class Meta:
        model=Task
        fields = ['id', 'indicator', 'organization', 'project', 'indicator_id', 
                  'project_id', 'organization_id', 'parent_task', 'targets']

class ProjectDetailSerializer(serializers.ModelSerializer):
    tasks = TaskSerializer(many=True, read_only=True)
    client = ClientSerializer(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), write_only=True, required=False, allow_null=True, source='client')
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), required=False, many=True, write_only=True, source='organizations')
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), many=True, required=False, write_only=True, source='indicators')
    organizations = serializers.SerializerMethodField()
    indicators = serializers.SerializerMethodField()

    def get_organizations(self, obj):
        user = self.context['request'].user
        if user.role == 'admin':
            queryset = obj.organizations.all()
        else:
            org = user.organization
            queryset = obj.organizations.filter(
                Q(parent_organization=org) | Q(id=org.id)
            )
        return OrganizationListSerializer(queryset, many=True, context=self.context).data

    def get_indicators(self, obj):
        user = self.context['request'].user
        if user.role == 'admin':
            queryset = obj.indicators.all()
        else:
            org = user.organization
            tasks = Task.objects.filter(organization=org, project=obj)
            indicator_ids = tasks.values_list('indicator_id', flat=True).distinct()
            queryset = Indicator.objects.filter(id__in=indicator_ids)
        return IndicatorSerializer(queryset, many=True, context=self.context).data
    
    class Meta:
        model=Project
        fields = ['id', 'name', 'client', 'start', 'end', 'description', 'tasks', 'client_id',
                  'organization_id', 'indicator_id', 'organizations', 'indicators', 'status']

    def validate(self, attrs):
        start = attrs.get('start', getattr(self.instance, 'start', None))
        end = attrs.get('end', getattr(self.instance, 'end', None))

        if start and end and end < start:
            raise serializers.ValidationError("Start date must be before end date")
        return attrs

    
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to edit projects.')
        organizations = validated_data.pop('organizations', [])
        inds = validated_data.pop('indicators', [])
        project = Project.objects.create(**validated_data)

        project.organizations.set(organizations)
        project.indicators.set(inds)
        return project
    
    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to edit projects.')

        organizations = validated_data.pop('organizations', [])
        indicators = validated_data.pop('indicators', [])

        # Update normal fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Add new organizations (append-only)
        existing_org_ids = set(
            ProjectOrganization.objects.filter(project=instance).values_list('organization_id', flat=True)
        )
        for org in organizations:
            if org.id not in existing_org_ids:
                ProjectOrganization.objects.create(project=instance, organization=org, added_by=user)

        # Add new indicators (append-only)
        existing_ind_ids = set(
            ProjectIndicator.objects.filter(project=instance).values_list('indicator_id', flat=True)
        )
        for indicator in indicators:
            if indicator.id not in existing_ind_ids:
                ProjectIndicator.objects.create(project=instance, indicator=indicator, added_by=user)
        return instance

class TargetForTaskSerializer(serializers.ModelSerializer):
    related_to = serializers.SerializerMethodField()
    class Meta:
        model = Target
        fields = ['id', 'start', 'end', 'amount','related_to','percentage_of_related',  ]
    def get_related_to(self, obj):
        if obj.related_to:
            return {
                'id': obj.related_to.id,
                'code': obj.related_to.indicator.code,
                'name': obj.related_to.indicator.name,
            }
        return None
class TargetSerializer(serializers.ModelSerializer):
    task = TaskSerializer(read_only=True)
    task_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, source='task')
    related_to = serializers.SerializerMethodField()
    related_to_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, required=False, allow_null=True, source='related_to')
    class Meta:
        model = Target
        fields = ['id', 'task', 'task_id', 'start', 'end', 'amount','related_to', 'related_to_id', 'percentage_of_related',  ]
    def get_related_to(self, obj):
        if obj.related_to:
            return {
                'id': obj.related_to.id,
                'code': obj.related_to.indicator.code,
                'name': obj.related_to.indicator.name,
            }
        return None
    
    def validate(self, attrs):
        print("Incoming validated attrs:", attrs)
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

