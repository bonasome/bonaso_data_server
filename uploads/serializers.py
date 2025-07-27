from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from uploads.models import NarrativeReport
from projects.models import ProjectOrganization
from profiles.serializers import ProfileListSerializer

class NarrativeReportSerializer(serializers.ModelSerializer):
    '''
    Serializer mostly for verifying correct file types.
    '''
    uploaded_by = ProfileListSerializer(read_only=True)

    class Meta:
        model = NarrativeReport
        fields = ['id', 'organization', 'project', 'uploaded_by', 'file','title','description',
                  'created_at', 'uploaded_by']

    def validate_file(self, value):
        allowed_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Only PDF and Word files are allowed.")
        return value
    
    def validate(self, attrs):
        user = self.context['request'].user
        org = attrs.get('organization')
        project = attrs.get('project')
        if not ProjectOrganization.objects.filter(organization=org, project=project).exists():
            raise serializers.ValidationError("This organization is not in this project.")
        
        if user.role != 'admin':
            if user.role not in ['meofficer', 'manager']:
                raise PermissionDenied("You do not have permissiont to perform this action.")
            if user.organization != org and not ProjectOrganization.objects.filter(project=project, organization=org, parent_organization=user.organization).exists():
                raise PermissionDenied("You can only upload reports for your own organization or a child organization.")
        return attrs