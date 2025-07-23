from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from projects.models import Project, Task, Client, Target, ProjectOrganization, ProjectActivity, ProjectDeadline, ProjectActivityComment, ProjectActivityOrganization, ProjectDeadlineOrganization
from projects.utils import get_valid_orgs, ProjectPermissionHelper
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
 
    class Meta:
        model=Task
        fields = ['id', 'indicator', 'organization', 'project', 'indicator_id', 
                  'project_id', 'organization_id']

class ProjectDetailSerializer(serializers.ModelSerializer):
    tasks = TaskSerializer(many=True, read_only=True)
    client = ClientSerializer(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), write_only=True, required=False, allow_null=True, source='client')
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), required=False, many=True, write_only=True, source='organizations')
    organizations = serializers.SerializerMethodField()

    def get_organizations(self, obj):
        user = self.context['request'].user

        if user.role in ['admin', 'client']:
            queryset = ProjectOrganization.objects.filter(project=obj)
        else:
            queryset = ProjectOrganization.objects.filter( project=obj
            ).filter(Q(organization=user.organization) | Q(parent_organization=user.organization))

        # Ensure related orgs are prefetched
        queryset = queryset.select_related('organization', 'parent_organization')

        # Build a map of orgs
        org_map = {
            org_link.organization.id: {
                'id': org_link.organization.id,
                'name': org_link.organization.name,
                'parent': {'id': org_link.parent_organization.id, 'name': org_link.parent_organization.name} if org_link.parent_organization else None,
                'children': []
            }
            for org_link in queryset
        }

        root_nodes = []
        for org_link in queryset:
            org_id = org_link.organization.id
            parent = org_link.parent_organization
            if parent and parent.id in org_map:
                org_map[parent.id]['children'].append(org_map[org_id])
            else:
                root_nodes.append(org_map[org_id])

        return root_nodes

    class Meta:
        model=Project
        fields = ['id', 'name', 'client', 'start', 'end', 'description', 'tasks', 'client_id',
                  'organization_id', 'organizations', 'status']

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
        project = Project.objects.create(**validated_data)

        self._add_organizations(project, organizations, user)
        return project


    @transaction.atomic
    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to edit projects.')

        organizations = validated_data.pop('organizations', [])

        # Update normal fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Add new organizations (append-only)
        self._add_organizations(instance, organizations, user)

        return instance
    
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
    organization_ids = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), many=True, write_only=True, required=False, source='organizations')
    comments = ProjectActivityCommentSerializer(read_only=True, many=True)

    class Meta:
        model = ProjectActivity
        fields = [
                    'id', 'project', 'project_id', 'organizations', 'organization_ids', 'start', 'end', 'comments',
                    'cascade_to_children', 'visible_to_all', 'category', 'status', 'name', 'description',
                ]
    
    def _set_organizations(self, activity, organizations):
        # Clear existing relationships first
        ProjectActivityOrganization.objects.filter(project_activity=activity).delete()
        orgs = organizations
        links = [
            ProjectActivityOrganization(project_activity=activity, organization=org)
            for org in orgs
        ]
        ProjectActivityOrganization.objects.bulk_create(links)

    def validate(self, attrs):
        user = self.context['request'].user
        project = attrs.get('project', getattr(self.instance, 'project', None))
        perm_manager = ProjectPermissionHelper(user=user, project=project)
        result = perm_manager.alter_switchboard(data=attrs, instance=(self.instance if self.instance else None))
        if not result.get('success', False):
            raise PermissionDenied(result.data)
        
        start = attrs.get('start', getattr(self.instance, 'start', None))
        end = attrs.get('end', getattr(self.instance, 'end', None))
                
        if start and end and end < start:
            raise serializers.ValidationError("Start date must be before end date")
        
        proj_start = project.start
        proj_end = project.end

        if start < proj_start or start > proj_end:
            raise serializers.ValidationError(f"Target start is outside the range of the project {proj_start}")
        
        if end > proj_end or end < proj_start:
            raise serializers.ValidationError(f"Target end is outside the range of the project {proj_end}")
        
        return result['data']
    
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])
        activity = ProjectActivity.objects.create(**validated_data)
        self._set_organizations(activity, organizations)
        activity.created_by = user
        activity.save()
        return activity

    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()
        self._set_organizations(instance, organizations)
        return instance
    
class ProjectDeadineOrganizationSerializer(serializers.ModelSerializer):
    organization = OrganizationListSerializer(read_only=True)
    class Meta:
        model = ProjectDeadlineOrganization
        fields = ['organization', 'organization_deadline', 'completed']

class ProjectDeadlineSerializer(serializers.ModelSerializer):
    project= ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, required=False, allow_null=True, source='project')
    organizations = ProjectDeadineOrganizationSerializer(read_only=True, many=True)
    organization_ids = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), many=True, write_only=True, required=False, source='organizations')

    class Meta:
        model = ProjectDeadline
        fields = ['id', 'project', 'project_id', 'organizations', 'organization_ids', 'deadline_date',
                'cascade_to_children', 'visible_to_all', 'name', 'description',
                ]
    
    def _set_organizations(self, deadline, organizations):
        # Clear existing relationships first
        ProjectDeadlineOrganization.objects.filter(deadline=deadline).delete()
        orgs = organizations
        links = [
            ProjectDeadlineOrganization(deadline=deadline, organization=org)
            for org in orgs
        ]
        ProjectDeadlineOrganization.objects.bulk_create(links)

    def validate(self, attrs):
        user = self.context['request'].user
        project = attrs.get('project', getattr(self.instance, 'project', None))
        perm_manager = ProjectPermissionHelper(user=user, project=project)
        result = perm_manager.alter_switchboard(data=attrs, instance=(self.instance if self.instance else None))
        if not result.get('success', False):
            raise PermissionDenied(result.data)
        
        date = attrs.get('deadline_date', getattr(self.instance, 'deadline_date', None))

        proj_start = project.start
        proj_end = project.end

        if date < proj_start or date > proj_end:
            raise serializers.ValidationError(f"Deadline date is outside the range of the project {proj_start} to {proj_end}. Not a bro move.")
        
        return result['data']
    
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])
        deadline = ProjectDeadline.objects.create(**validated_data)
        self._set_organizations(deadline, organizations)
        deadline.created_by = user
        deadline.save()
        return deadline

    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        organizations = validated_data.pop('organizations', [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()
        self._set_organizations(instance, organizations)
        return instance