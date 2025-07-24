from rest_framework import serializers
from django.shortcuts import get_object_or_404
from django.db.models import Q
from projects.serializers import TaskSerializer
from projects.models import Task, ProjectOrganization
from social.models import SocialMediaPost, SocialMediaPostTasks, SocialMediaPostFlag
from social.utils import user_has_post_access
from datetime import date
from collections import defaultdict
from rest_framework.exceptions import PermissionDenied

class SocialMediaPostFlagSerializer(serializers.ModelSerializer):
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
        model=SocialMediaPostFlag
        fields = [
            'id', 'reason', 'created_by', 'created_at', 'resolved',
            'resolved_reason', 'resolved_by', 'resolved_at'
        ]

class SocialMediaPostSerializer(serializers.ModelSerializer):
    tasks = TaskSerializer(read_only=True, many=True)
    task_ids = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(), write_only=True, many=True, required=True
    )
    flags = SocialMediaPostFlagSerializer(read_only=True, many=True)

    class Meta:
        model = SocialMediaPost
        fields = [
            'id', 'name', 'description', 'likes', 'comments', 'views',
            'platform', 'other_platform', 'link_to_post', 'published_at',
            'tasks', 'task_ids', 'created_at', 'flags'
        ]

    def validate(self, attrs):
        user = self.context['request'].user
        task_list = attrs.get('task_ids') or getattr(self.instance, 'tasks', None)

        if not task_list:
            raise serializers.ValidationError({'task_ids': 'This field is required.'})

        
        update_tasks = 'task_ids' in self.initial_data 

        org = None
        if update_tasks:
            for task in task_list:
                if org and task.organization != org:
                    raise serializers.ValidationError('All tasks must belong to the same organization.')
                org = task.organization

                if user.role != 'admin':
                    if task.organization != user.organization and not ProjectOrganization.objects.filter(
                        parent_organization=user.organization,
                        organization=task.organization,
                        project=task.project
                    ).exists():
                        raise PermissionDenied('You do not have permission to use this task.')

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
        task_ids = validated_data.pop('task_ids', None)
        update_tasks = 'task_ids' in self.initial_data 
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if update_tasks:
            SocialMediaPostTasks.objects.filter(post=instance).delete()
            if task_ids: 
                for task in task_ids:
                    SocialMediaPostTasks.objects.create(post=instance, task=task)

        return instance