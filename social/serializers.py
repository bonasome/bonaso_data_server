from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from datetime import date

from profiles.serializers import ProfileListSerializer
from projects.serializers import TaskSerializer
from projects.models import Task, ProjectOrganization
from organizations.models import Organization
from social.models import SocialMediaPost, SocialMediaPostTasks
from flags.serializers import FlagSerializer
from indicators.models import Indicator
from organizations.serializers import OrganizationListSerializer

class SocialMediaPostSerializer(serializers.ModelSerializer):
    '''
    Serializer for managing data around social media posts.
    '''
    tasks = TaskSerializer(read_only=True, many=True)
    task_ids = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(), 
        source='tasks',
        write_only=True, 
        many=True, 
        required=True
    )
    flags = FlagSerializer(read_only=True, many=True)
    organization = OrganizationListSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(
        queryset=Organization.objects.all(), 
        source='organization',
        write_only=True, 
        required=True
    )
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)

    class Meta:
        model = SocialMediaPost
        fields = [
            'id', 'name', 'description', 'likes', 'comments', 'views', 'reach',
            'platform', 'other_platform', 'link_to_post', 'published_at', 'organization', 'organization_id',
            'tasks', 'task_ids', 'created_at', 'flags', 'updated_at', 'created_by',
            'updated_by',
        ]

    def validate(self, attrs):
        '''
        Permission checks and make sure that a platform is provided (specifying if other).
        '''
        user = self.context['request'].user
        if user.role not in ['meofficer', 'manager', 'admin']:
            raise PermissionDenied('You do not have permission to perform this action.')
        
        #make sure that an irg is attached
        org = attrs.get('organization')
        if not org:
            raise serializers.ValidationError({'organization': 'This field is required.'})
        
        #and a list of tasks
        tasks = attrs.get('tasks')
        if not tasks:
            raise serializers.ValidationError({'Tasks': 'This field is required.'})

        #validate that each task belongs to the org, has a social ind, and if not admin, is either that orgs task
        # or a task for a child org in a valid project
        # we don't need to perm check org since we'll catch issues with org not being a valid child here
        for task in tasks:
            if task.indicator.category != Indicator.Category.SOCIAL:
                raise serializers.ValidationError({'Tasks': f'Task associated with indicator {task.indicator.name} is not attachable to a social media post.'})
            if task.organization != org:
                raise serializers.ValidationError({'Tasks': 'Task must belong to the selected organization.'})
            if user.role != 'admin':
                if task.organization != user.organization and not ProjectOrganization.objects.filter(organization=task.organization, project=task.project, parent_organization=user.organization).exists():
                    raise PermissionDenied('You do not have permission to attach this task.')

       
        #make sure platform info is provided
        platform = attrs.get('platform') or getattr(self.instance, 'platform', None)
        if platform == SocialMediaPost.Platform.OTHER:
            other = attrs.get('other_platform') or getattr(self.instance, 'other_platform', None)
            if not other:
                raise serializers.ValidationError({'other_platform': 'Please specify the platform.'})
            
        published_at = attrs.get('published_at') or getattr(self.instance, 'published_at', None)
        # Parse string to date if needed
        if isinstance(published_at, str):
            published_at = date.fromisoformat(published_at)

        # Ensure published_at is a date
        if not isinstance(published_at, date):
            raise serializers.ValidationError({'published_at': 'Invalid or missing published date.'})

        has_metrics = any(attrs.get(field) for field in ['likes', 'comments', 'views', 'reach'])
        if has_metrics and date.today() < published_at:
            raise serializers.ValidationError('Cannot provide metrics for a post scheduled in the future.')

        return attrs
    
    def create(self, validated_data):
        user = self.context['request'].user
        tasks = validated_data.pop('tasks', [])

        post = SocialMediaPost.objects.create(
            created_by=user,
            **validated_data
        )
        for task in tasks:
            SocialMediaPostTasks.objects.create(post=post, task=task)

        return post

    def update(self, instance, validated_data):
        user = self.context['request'].user
        tasks = validated_data.pop('tasks', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()

        SocialMediaPostTasks.objects.filter(post=instance).delete()
        for task in tasks:
            SocialMediaPostTasks.objects.create(post=instance, task=task)

        return instance