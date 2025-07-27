from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from projects.serializers import TaskSerializer
from projects.models import Task, ProjectOrganization
from social.models import SocialMediaPost, SocialMediaPostTasks
from flags.serializers import FlagSerializer



class SocialMediaPostSerializer(serializers.ModelSerializer):
    '''
    Serializer for managing data around social media posts.
    '''
    tasks = TaskSerializer(read_only=True, many=True)
    task_ids = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(), write_only=True, many=True, required=True
    )
    flags = FlagSerializer(read_only=True, many=True)

    class Meta:
        model = SocialMediaPost
        fields = [
            'id', 'name', 'description', 'likes', 'comments', 'views',
            'platform', 'other_platform', 'link_to_post', 'published_at',
            'tasks', 'task_ids', 'created_at', 'flags'
        ]

    def validate(self, attrs):
        '''
        Permission checks and make sure that a platform is provided (specifying if other).
        '''
        user = self.context['request'].user
        task_list = attrs.get('task_ids') or getattr(self.instance, 'tasks', None)
        if user.role not in ['meofficer', 'manager', 'admin']:
            raise PermissionDenied('You do not have permission to perform this action.')
        if not task_list:
            raise serializers.ValidationError({'task_ids': 'This field is required.'})

        
        update_tasks = 'task_ids' in self.initial_data 
        #check that all tasks are with the same org
        org = None
        if update_tasks:
            for task in task_list:
                if org and task.organization != org:
                    raise serializers.ValidationError('All tasks must belong to the same organization.')
                org = task.organization

                #check that task is associated with the organization or their child
                if user.role != 'admin':
                    if task.organization != user.organization and not ProjectOrganization.objects.filter(
                        parent_organization=user.organization,
                        organization=task.organization,
                        project=task.project
                    ).exists():
                        raise PermissionDenied('You do not have permission to use this task.')
       
        #make sure platform info is provided
        platform = attrs.get('platform') or getattr(self.instance, 'platform', None)
        if platform == SocialMediaPost.Platform.OTHER:
            other = attrs.get('other_platform') or getattr(self.instance, 'other_platform', None)
            if not other:
                raise serializers.ValidationError({'other_platform': 'Please specify the platform.'})

        return attrs

    def create(self, validated_data):
        user = self.context['request'].user
        task_ids = validated_data.pop('task_ids', [])

        post = SocialMediaPost.objects.create(
            created_by=user,
            **validated_data
        )

        for task in task_ids:
            print(task)
            SocialMediaPostTasks.objects.create(post=post, task=task)

        return post

    def update(self, instance, validated_data):
        user = self.context['request'].user
        task_ids = validated_data.pop('task_ids', None)
        update_tasks = 'task_ids' in self.initial_data 
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()

        if update_tasks:
            SocialMediaPostTasks.objects.filter(post=instance).delete()
            if task_ids: 
                for task in task_ids:
                    SocialMediaPostTasks.objects.create(post=instance, task=task)

        return instance