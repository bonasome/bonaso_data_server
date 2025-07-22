from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from projects.models import Project, Task, Client, Target, ProjectOrganization, ProjectActivity, ProjectActivityComment, ProjectActivityOrganization
from projects.utils import get_valid_orgs
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
        fields = ['id', 'name', 'full_name']

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
        if user.role == 'admin' or user.role=='client':
            queryset = obj.organizations.all()
        else:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            queryset = Organization.objects.filter(
                Q(task__organization=user.organization) | Q(task__organization__in=child_orgs)
            )
        return OrganizationListSerializer(queryset, many=True, context=self.context).data

    def get_indicators(self, obj):
        user = self.context['request'].user
        if user.role == 'admin' or user.role == 'client':
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


    @transaction.atomic
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to edit projects.')
        organizations = validated_data.pop('organizations', [])
        indicators = validated_data.pop('indicators', [])
        project = Project.objects.create(**validated_data)

        self._add_organizations(project, organizations, user)
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

        return instance

class TargetForTaskSerializer(serializers.ModelSerializer):
    related_to = serializers.SerializerMethodField()
    class Meta:
        model = Target
        fields = ['id', 'start', 'end', 'amount','related_to','percentage_of_related']
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
    related_to = TaskSerializer(read_only=True)
    related_to_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, required=False, allow_null=True, source='related_to')
    related_as_number = serializers.SerializerMethodField()
    achievement = serializers.SerializerMethodField()
    
    def get_related_as_number(self, obj):
        from respondents.models import Interaction, InteractionFlag, InteractionSubcategory
        from events.models import Event, DemographicCount, CountFlag
        if not obj.related_to:
            return None
        amount = 0
        if obj.related_to.indicator.indicator_type == 'Respondent':
            flagged_irs = InteractionFlag.objects.values_list('interaction_id', flat=True)
            irs = Interaction.objects.filter(task=obj.related_to, interaction_date__gte=obj.start, interaction_date__lte=obj.end).exclude(id__in=flagged_irs)
            for ir in irs:
                total = 1
                if ir.task.indicator.require_numeric and ir.task.indicator.subcategories.exists():
                    for cat in InteractionSubcategory.objects.filter(interaction=ir):
                        total+= cat.numeric_component
                elif ir.task.indicator.require_numeric:
                    total += ir.numeric_component
                amount += total
            flagged_counts = CountFlag.objects.values_list('count_id', flat=True)
            counts = DemographicCount.objects.filter(task=obj.related_to, event__event_date__gte=obj.start, event__event_date__lte=obj.end).exclude(id__in=flagged_counts)
            for dc in counts:
                amount += dc.count
        elif obj.task.indicator.indicator_type == 'Count':
            flagged_counts = CountFlag.objects.values_list('count_id', flat=True)
            counts = DemographicCount.objects.filter(task=obj.related_to, event__event_date__gte=obj.start, event__event_date__lte=obj.end).exclude(id__in=flagged_counts)
            for dc in counts:
                amount += dc.count
        return amount

    def get_achievement(self, obj):
        from respondents.models import Interaction, InteractionSubcategory, InteractionFlag
        from events.models import Event, DemographicCount, CountFlag
        amount = 0
        if obj.task.indicator.indicator_type == 'Respondent':
            flagged_irs = InteractionFlag.objects.values_list('interaction_id', flat=True)
            interactions = Interaction.objects.filter(task=obj.task, interaction_date__gte=obj.start, interaction_date__lte=obj.end).exclude(id__in=flagged_irs)
            for ir in interactions:
                if ir.subcategories.exists() and ir.task.indicator.require_numeric:
                    for cat in InteractionSubcategory.objects.filter(interaction=ir):
                        amount += cat.numeric_component
                elif ir.task.indicator.require_numeric:
                    amount += ir.numeric_component
                else:
                    amount += 1
            flagged_counts = CountFlag.objects.values_list('count_id', flat=True)
            counts = DemographicCount.objects.filter(task=obj.task, event__event_date__gte=obj.start, event__event_date__lte=obj.end).exclude(id__in=flagged_counts)
            for dc in counts:
                amount += dc.count
        elif obj.task.indicator.indicator_type == 'Count':
            flagged_counts = CountFlag.objects.values_list('count_id', flat=True)
            counts = DemographicCount.objects.filter(task=obj.task, event__event_date__gte=obj.start, event__event_date__lte=obj.end).exclude(id__in=flagged_counts)
            for dc in counts:
                amount += dc.count
        elif obj.task.indicator.indicator_type == 'Event_No':
            amount += Event.objects.filter(tasks=obj.task, status= Event.EventStatus.COMPLETED, event_date__gte=obj.start, event_date__lte=obj.end).count()
        elif obj.task.indicator.indicator_type == 'Org_Event_No':
            events = Event.objects.filter(tasks=obj.task, status= Event.EventStatus.COMPLETED, event_date__gte=obj.start, event_date__lte=obj.end)
            for event in events:
                amount += event.organizations.count()
        return amount

    class Meta:
        model = Target
        fields = ['id', 'task', 'task_id', 'start', 'end', 'amount','related_to', 'related_to_id', 
                'related_as_number', 'percentage_of_related', 'achievement']

    
    def validate(self, attrs):
        task = attrs.get('task', getattr(self.instance, 'task', None))
        
        user = self.context['request'].user
        if user.role not in ['meofficer', 'manager', 'admin']:
            raise PermissionDenied("You do not have permission to create targets.")
        
        if user.role != 'admin':
            is_child = ProjectOrganization.objects.filter(
                organization=task.organization,
                parent_organization=user.organization
            ).exists()
            if not is_child:
                # This includes the case where instance.organization == user.organization
                raise PermissionDenied("You may only assign targets to your child organizations.")
        
        related = attrs.get('related_to')
        if not task:
            raise serializers.ValidationError({'task_id': 'Task not found.'})
        
        if related and related == task:
            raise serializers.ValidationError({'related_to_id': 'A target cannot use its own assigned task as a reference.'})
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
        
        proj_start = task.project.start
        proj_end = task.project.end

        if start < proj_start or start > proj_end:
            raise serializers.ValidationError(f"Target start is outside the range of the project {proj_start}")
        
        if end > proj_end or end < proj_start:
            raise serializers.ValidationError(f"Target end is outside the range of the project {proj_end}")
        
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
class ProjectActivityCommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField(read_only=True)
    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "first_name": obj.created_by.first_name,
                "last_name": obj.created_by.last_name,
            }
        
    class Meta:
        model=ProjectActivityComment
        fields = ['id', 'activity', 'author', 'content', 'created']

class ProjectActivitySerializer(serializers.ModelSerializer):
    project= ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, required=False, allow_null=True, source='project')
    organizations = OrganizationListSerializer(read_only=True, many=True)
    organization_ids = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), many=True, write_only=True, required=False, allow_null=True, source='organizations')
    comments = ProjectActivityCommentSerializer(read_only=True, many=True)

    class Meta:
        model = ProjectActivity
        fields = ['id', 'project', 'project_id', 'organizations', 'organization_ids', 'start', 'end', 'comments',
                'cascade_to_children', 'visible_to_all', 'category', 'status', 'name', 'description',
                ]
    
    def _set_organizations(self, activity, organizations, user, cascade_to_children):
        # Clear existing relationships first
        ProjectActivityOrganization.objects.filter(project_activity=activity).delete()

        orgs = organizations
        if not orgs:
            orgs = [user.organization]
        print(cascade_to_children)
        if cascade_to_children:
            org_ids = [org.id for org in orgs]
            # Ensure you're collecting orgs, not ProjectOrganization objects
            child_orgs = ProjectOrganization.objects.filter(
                project=activity.project,
                parent_organization_id__in=org_ids  # cascade from each selected org, not user only
            )
            if child_orgs:
                child_orgs = [org.organization for org in child_orgs]
            orgs = list(set(orgs) | set(child_orgs))  # de-duplicate
        else:
            orgs = organizations
        links = [
            ProjectActivityOrganization(project_activity=activity, organization=org)
            for org in orgs
        ]
        ProjectActivityOrganization.objects.bulk_create(links)

    def validate(self, attrs):
        user = self.context['request'].user
        project = attrs.get('project', getattr(self.instance, 'project', None))
        start = attrs.get('start', getattr(self.instance, 'start', None))
        end = attrs.get('end', getattr(self.instance, 'end', None))
        visible_to_all = str(attrs.get('visible_to_all', getattr(self.instance, 'visible_to_all', False))).lower() in ['true', '1']
        organizations = attrs.get('organizations', getattr(self.instance, 'organizations', []))

        cascade_to_children = str(attrs.get('cascade_to_children', getattr(self.instance, 'cascade_to_children', False))).lower() in ['true', '1']
        if user.role not in ['admin', 'meofficer', 'manager']:
            raise PermissionDenied('You do not have permission to create project activities.')
        if user.role != 'admin':
            if visible_to_all:
                raise PermissionDenied('Only an admin amy make an activity visible to all members of a project')
            for organization in organizations:
                if not user.organization == organization and not ProjectOrganization.objects.filter(project=project, organization=organization, parent_organization=user.organization).exists():
                    raise PermissionDenied('You may not add organizations that are not your organizaiton or a child organization')
                
        if start and end and end < start:
            raise serializers.ValidationError("Start date must be before end date")
        
        proj_start = project.start
        proj_end = project.end

        if start < proj_start or start > proj_end:
            raise serializers.ValidationError(f"Target start is outside the range of the project {proj_start}")
        
        if end > proj_end or end < proj_start:
            raise serializers.ValidationError(f"Target end is outside the range of the project {proj_end}")
        return attrs
    
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])
        cascade_to_children = validated_data.get('cascade_to_children', False)
        activity = ProjectActivity.objects.create(**validated_data)
        print(cascade_to_children)
        self._set_organizations(activity, organizations, user, cascade_to_children)
        activity.created_by = user
        activity.save()
        return activity

    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])
        cascade_to_children = validated_data.get('cascade_to_children', False)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()
        print(cascade_to_children)
        self._set_organizations(instance, organizations, user, cascade_to_children)
        return instance