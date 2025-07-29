from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from django.db import transaction
from django.db.models import Q

from projects.exceptions import ConflictError
from projects.models import Project, Task, Client, Target, ProjectOrganization, ProjectActivity, ProjectDeadline, ProjectActivityComment, ProjectActivityOrganization, ProjectDeadlineOrganization
from projects.utils import ProjectPermissionHelper, test_child_org
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from indicators.models import Indicator
from indicators.serializers import IndicatorSerializer
from profiles.serializers import ProfileListSerializer
from analysis.utils.aggregates import get_achievement

class ClientSerializer(serializers.ModelSerializer):
    '''
    Simple serializer for viewing/editing clients. Only admins have rights to do this.
    '''
    class Meta:
        model = Client
        fields = ['id', 'name', 'full_name']

    def validate(self, attrs):
        request = self.context.get('request')
        user = getattr(request, 'user', None)

        if not user or user.role != 'admin':
            raise PermissionDenied('You do not have permission to manage clients.')
        return attrs


class ProjectListSerializer(serializers.ModelSerializer):
    '''
    Simple list serializer with minimal project information.
    '''
    client = ClientSerializer(read_only=True)
    class Meta:
        model = Project
        fields = ['id', 'name', 'client', 'start', 'end', 'status']

class TaskSerializer(serializers.ModelSerializer):
    '''
    Serializer for viewing tasks.
    '''
    indicator = IndicatorSerializer(read_only=True)
    project = ProjectListSerializer(read_only=True)
    organization = OrganizationListSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization')
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), write_only=True, source='indicator')
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, source='project')
    display_name = serializers.SerializerMethodField(read_only=True)

    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()

    
    class Meta:
        model=Task
        fields = ['id', 'indicator', 'organization', 'project', 'indicator_id', 
                  'project_id', 'organization_id', 'display_name']
        

    def validate(self, attrs):
        user = self.context.get('request').user if self.context.get('request') else None
        organization = attrs.get('organization')
        indicator = attrs.get('indicator')
        project = attrs.get('project')
        if not organization or not project or not indicator:
            raise serializers.ValidationError(
                    f"This task requires a project, indicator, and organization."
                )
        if Task.objects.filter(project=project, organization=organization, indicator=indicator).exists():
            raise serializers.ValidationError('This task already exists.')
        if user.role != 'admin':
            #only allow non admins to create tasks for their children
            if not test_child_org(user, organization, project):
                raise PermissionDenied('You do not have permission to create this task.')
        if not ProjectOrganization.objects.filter(project=project, organization=organization).exists():
            raise serializers.ValidationError('This organization is not a part of this project.')
        for prereq in indicator.prerequisites.all():
            if prereq and not Task.objects.filter(project=project, organization=organization, indicator=prereq).exists():
                raise serializers.ValidationError(
                    f"This task's indicator has a prerequisite '{prereq.name}'. Please assign that indicator as a task first."
                )
        return attrs
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        task= Task.objects.create(**validated_data)
        task.created_by = user
        task.save()
        return task

class ProjectDetailSerializer(serializers.ModelSerializer):
    '''
    A more detailed project serializer used for detail views that contains related information about
    organizations and tasks. 
    '''
    tasks = TaskSerializer(many=True, read_only=True)
    client = ClientSerializer(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), write_only=True, required=False, allow_null=True, source='client')
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), required=False, many=True, write_only=True, source='organizations')
    organizations = serializers.SerializerMethodField()
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    def get_organizations(self, obj):
        '''
        Vary what organiations users see based on their role/org and send the orgs with useful
        information about their relationship to the project.
        '''
        user = self.context['request'].user

        if user.role in ['admin', 'client']:
            queryset = ProjectOrganization.objects.filter(project=obj)
        else:
            #others can only see orgs that are related to them
            queryset = ProjectOrganization.objects.filter( project=obj
            ).filter(Q(organization=user.organization) | Q(parent_organization=user.organization))

        # Ensure related orgs are prefetched
        queryset = queryset.select_related('organization', 'parent_organization')

        # Build a map of orgs (incluidng parent/children makes the front end a lot simpler)
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
        fields = [
            'id', 'name', 'client', 'start', 'end', 'description', 'tasks', 'client_id',
            'organization_id', 'organizations', 'status', 'created_by', 'created_at', 'updated_by',
            'updated_at'
        ]

    def validate(self, attrs):
        # Use incoming value if present, otherwise fall back to existing value on the instance
        start = attrs.get('start') or getattr(self.instance, 'start', None)
        end = attrs.get('end') or getattr(self.instance, 'end', None)

        if start and end and end < start:
            raise serializers.ValidationError("End date must be after start date.")

        return attrs

    #helper to add/set organizations
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
        project.created_by = user
        project.save()
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
        instance.updated_by = user
        instance.save()

        # Add new organizations (append-only)
        self._add_organizations(instance, organizations, user)

        return instance
    
class TargetSerializer(serializers.ModelSerializer):
    '''
    Serializer for viewing targets.
    '''
    task = TaskSerializer(read_only=True)
    task_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, source='task')
    related_to = TaskSerializer(read_only=True)
    related_to_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, required=False, allow_null=True, source='related_to')
    related_as_number = serializers.SerializerMethodField()
    achievement = serializers.SerializerMethodField()
    
    def get_related_as_number(self, obj):
        '''
        Get the actual numeric value that a related to percentage represents at a given moment.
        '''
        user = self.context.get('request').user
        if not obj.related_to:
            return None
        return get_achievement(user, obj.related_to)

    def get_achievement(self, obj):
        '''
        Get the actual number that has been acheived. Works similar to the above function.
        '''
        user = self.context.get('request').user
        return get_achievement(user, obj)

    class Meta:
        model = Target
        fields = ['id', 'task', 'task_id', 'start', 'end', 'amount','related_to', 'related_to_id', 
                'related_as_number', 'percentage_of_related', 'achievement']

    
    def validate(self, attrs):
        task = attrs.get('task', getattr(self.instance, 'task', None))
        
        ###===Permission Check===###
        user = self.context['request'].user
        if user.role not in ['meofficer', 'manager', 'admin']:
            raise PermissionDenied("You do not have permission to create targets.")
        
        if user.role != 'admin':
            #if not an admin, only allow users to assign targets to their children
            is_child = ProjectOrganization.objects.filter(
                organization=task.organization,
                parent_organization=user.organization,
                project=task.project
            ).exists()
            if not is_child:
                # This includes the case where instance.organization == user.organization
                raise PermissionDenied("You may only assign targets to your child organizations.")
        
        ###===VALIDATION===###, error messages should help explain what each of these does
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
        
        #make sure target is within the range of the project
        proj_start = task.project.start
        proj_end = task.project.end

        if start < proj_start or start > proj_end:
            raise serializers.ValidationError(f"Target start is outside the range of the project {proj_start}")
        
        if end > proj_end or end < proj_start:
            raise serializers.ValidationError(f"Target end is outside the range of the project {proj_end}")
        
        #check if this overlaps with another target for the same task
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
    '''
    Theoretical serializer for when we implement comments for activities.
    '''
    author = ProfileListSerializer()
        
    class Meta:
        model=ProjectActivityComment
        fields = ['id', 'activity', 'author', 'content', 'created']

class ProjectActivitySerializer(serializers.ModelSerializer):
    '''
    Serializer for managing project activities.
    '''
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
        '''
        Set the organizations attached to this activity. Clear existing on update
        '''
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
        
        #see perm manager for more information on managing permissions
        perm_manager = ProjectPermissionHelper(user=user, project=project)
        result = perm_manager.alter_switchboard(data=attrs, instance=(self.instance if self.instance else None))
        if not result.get('success', False):
            raise PermissionDenied(result.get('data'))
        
        #date validation, make sure it lines up and is within the project dates
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
    

class ProjectDeadlineSerializer(serializers.ModelSerializer):
    '''
    Very similar concept to the above. 
    '''
    project= ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, required=False, allow_null=True, source='project')
    organizations = serializers.SerializerMethodField()
    organization_ids = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), many=True, write_only=True, required=False, source='organizations')

    def get_organizations(self, obj):
        org_links = ProjectDeadlineOrganization.objects.filter(deadline=obj)
        orgs = []
        for org in org_links:
            orgs.append({'id': org.organization.id, 'name': org.organization.name, 
                         'organization_deadline': org.organization_deadline, 'completed': org.completed})
        return orgs
    
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
            raise PermissionDenied(result.get('data'))
        
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