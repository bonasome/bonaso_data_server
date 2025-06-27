from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from projects.models import Project, Task, Client, Target, ProjectIndicator, ProjectOrganization
from organizations.models import Organization
from indicators.models import Indicator
from organizations.serializers import OrganizationListSerializer
from indicators.serializers import IndicatorSerializer
from rest_framework.exceptions import APIException

class ConflictError(APIException):
    status_code = 409
    default_detail = 'Conflict: This resource overlaps with an existing one.'
    default_code = 'conflict'

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['id', 'name']

    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or user.role != 'admin':
            raise PermissionDenied('You do not have permission to manage clients.')

        return super().create(validated_data)


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

    targets = serializers.SerializerMethodField()

    def get_targets(self, obj):
        request = self.context.get('request')
        if request and request.query_params.get('include_targets') == 'true':
            return TargetForTaskSerializer(obj.target_set.all(), many=True, context=self.context).data
        return None
    
    class Meta:
        model=Task
        fields = ['id', 'indicator', 'organization', 'project', 'indicator_id', 
                  'project_id', 'organization_id', 'targets']

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
        # Use incoming value if present, otherwise fall back to existing value on the instance
        start = attrs.get('start') or getattr(self.instance, 'start', None)
        end = attrs.get('end') or getattr(self.instance, 'end', None)

        if start and end and end < start:
            raise serializers.ValidationError("End date must be after start date.")

        return attrs

    def _add_organizations(self, project, organizations, user):
        existing_org_ids = set(
            ProjectOrganization.objects.filter(project=project).values_list('organization_id', flat=True)
        )
        new_links = [
            ProjectOrganization(project=project, organization=org, added_by=user)
            for org in organizations if org.id not in existing_org_ids
        ]
        ProjectOrganization.objects.bulk_create(new_links)

    def _add_indicators(self, project, indicators, user):
        existing_ind_ids = set(
            ProjectIndicator.objects.filter(project=project).values_list('indicator_id', flat=True)
        )
        incoming_ind_ids = {ind.id for ind in indicators}

        new_links = []
        for indicator in indicators:
            prereq = getattr(indicator, 'prerequisite', None)
            if prereq and prereq.id not in existing_ind_ids and prereq.id not in incoming_ind_ids:
                raise serializers.ValidationError(
                    f"Indicator '{indicator}' has a prerequisite that must be added first."
                )
            if indicator.id not in existing_ind_ids:
                new_links.append(ProjectIndicator(project=project, indicator=indicator, added_by=user))

        ProjectIndicator.objects.bulk_create(new_links)


    @transaction.atomic
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to edit projects.')
        organizations = validated_data.pop('organizations', [])
        indicators = validated_data.pop('indicators', [])
        project = Project.objects.create(**validated_data)

        self._add_organizations(project, organizations, user)
        self._add_indicators(project, indicators, user)
        return project


    @transaction.atomic
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
        self._add_organizations(instance, organizations, user)
        self._add_indicators(instance, indicators, user)

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
        task = attrs.get('task', getattr(self.instance, 'task', None))
        org = attrs.get('organization', getattr(self.instance, 'organization', None)) \
            or getattr(task, 'organization', None)
        
        user = self.context['request'].user
        if user.role not in ['meofficer', 'manager', 'admin']:
            raise serializers.ValidationError("You do not have permission to create targets.")
        if user.role != 'admin' and org.parent_organization.id != user.organization_id:
            raise serializers.ValidationError("You may only assign tasks to your child organizations.")
        
        related = attrs.get('related_to')
        if not task:
            raise serializers.ValidationError({'task_id': 'Task not found.'})
        
        if related and related == task:
            raise serializers.ValidationError({'related_to_id': 'A task cannot reference itself.'})
        if related and related.project != task.project:
            raise serializers.ValidationError({'related_to_id': 'Related target must belong to the same project.'})

        if related and related.organization != task.organization:
            raise serializers.ValidationError({'related_to_id': 'Related target must be assigned to the same organization.'})
        
        if not attrs.get('amount') and (not related or not attrs.get('percentage_of_related')):
            raise serializers.ValidationError("Either 'amount' or both 'related_to' and 'percentage_of_related' must be provided.")
        
        if attrs.get('amount') and (related and attrs.get('percentage_of_related')):
            raise serializers.ValidationError("Target expected either amount or percentage of related task but got both instead.")
        
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
                raise ConflictError("This target overlaps with an existing target.")
        
        return attrs

