from rest_framework import serializers
from projects.models import Project, ProjectIndicator, ProjectOrganization, Task

class ProjectsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name', 'client', 'start', 'end', 'status', 'description']

class ProjectIndicatorSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='indicator.id')
    name = serializers.CharField(source='indicator.name')
    code = serializers.CharField(source='indicator.code')
    description = serializers.CharField(source='indicator.description')
    class Meta:
        model = ProjectIndicator
        fields = ['id', 'name', 'code', 'description']

class ProjectOrganizationSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='organization.id')
    name = serializers.CharField(source='organization.name')
    class Meta:
        model = ProjectOrganization
        fields = ['id', 'name']

class ProjectTaskSerializer(serializers.ModelSerializer):
    org = serializers.CharField(source='organization.id')
    indicator = serializers.CharField(source='indicator.id')
    class Meta:
        model = Task
        fields = ['org', 'indicator']