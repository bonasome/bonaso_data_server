from rest_framework import serializers
from profiles.models import FavoriteProject, FavoriteRespondent, FavoriteTask

from respondents.serializers import RespondentSerializer
from respondents.models import Respondent

from projects.serializers import TaskSerializer, ProjectDetailSerializer
from projects.models import Task, Project
from django.contrib.auth import get_user_model

User = get_user_model()

class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model=User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'organization', 'role', 'is_active']
        read_only_fields = ['id']

    def get_fields(self):
        fields = super().get_fields()
        user = self.context['request'].user

        if user.role != 'admin':
            fields['is_active'].read_only = True

        if user.role != 'admin':
            fields['role'].read_only = True
            fields['organization'].read_only = True

        return fields

class FavoriteTaskSerializer(serializers.ModelSerializer):
    task = TaskSerializer(read_only=True)
    task_id = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(), write_only=True, source='task'
    )
    class Meta:
        model = FavoriteTask
        fields = ['id', 'task', 'task_id']

class FavoriteProjectSerializer(serializers.ModelSerializer):
    project = ProjectDetailSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(), write_only=True, source='project'
    )
    class Meta:
        model = FavoriteProject
        fields = ['id', 'project', 'project_id']

class FavoriteRespondentSerializer(serializers.ModelSerializer):
    respondent = RespondentSerializer(read_only=True)
    respondent_id = serializers.PrimaryKeyRelatedField(
        queryset=Respondent.objects.all(), write_only=True, source='respondent'
    )
    class Meta:
        model = FavoriteRespondent
        fields = ['id', 'respondent', 'respondent_id']