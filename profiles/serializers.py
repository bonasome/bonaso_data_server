from rest_framework import serializers
from profiles.models import FavoriteProject, FavoriteRespondent, FavoriteEvent


from respondents.models import Respondent

from projects.serializers import ProjectListSerializer, ClientSerializer
from projects.models import Task, Project, Client
from events.models import Event
from events.serializers import EventSerializer
from django.contrib.auth import get_user_model

User = get_user_model()

from organizations.serializers import OrganizationListSerializer
from organizations.models import Organization

class ProfileListSerializer(serializers.ModelSerializer):
    organization = OrganizationListSerializer(read_only=True)
    class Meta:
        model=User
        fields = ['id', 'first_name', 'last_name', 'organization']

class ProfileSerializer(serializers.ModelSerializer):
    organization_detail = OrganizationListSerializer(source='organization', read_only=True)
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True)
    client_organization = ClientSerializer(read_only=True)

    class Meta:
        model=User
        fields = ['id', 'username', 'first_name', 'last_name', 'email','organization_detail', 'organization', 'role', 'is_active', 'client_organization']
        read_only_fields = ['id']

    def get_fields(self):
        fields = super().get_fields()
        user = self.context['request'].user

        if user.role != 'admin':
            fields['is_active'].read_only = True
            fields['role'].read_only = True

        return fields

class FavoriteEventSerializer(serializers.ModelSerializer):
    event = EventSerializer(read_only=True)
    event_id = serializers.PrimaryKeyRelatedField(
        queryset=Event.objects.all(), write_only=True, source='event'
    )
    class Meta:
        model = FavoriteEvent
        fields = ['id', 'event', 'event_id']

class FavoriteProjectSerializer(serializers.ModelSerializer):
    project = ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(), write_only=True, source='project'
    )
    class Meta:
        model = FavoriteProject
        fields = ['id', 'project', 'project_id']

class FavoriteRespondentSerializer(serializers.ModelSerializer):
    respondent = serializers.SerializerMethodField()
    respondent_id = serializers.PrimaryKeyRelatedField(
        queryset=Respondent.objects.all(), write_only=True, source='respondent'
    )
    def get_respondent(self, obj):
        return "screw off django"
    class Meta:
        model = FavoriteRespondent
        fields = ['id', 'respondent', 'respondent_id']