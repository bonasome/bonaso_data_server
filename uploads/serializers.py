from rest_framework import serializers
from uploads.models import NarrativeReport

class NarrativeReportSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = NarrativeReport
        fields = ['id', 'organization', 'project', 'uploaded_by', 'file','title','description',
                  'created_at', 'uploaded_by']

    def validate_file(self, value):
        allowed_types = ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Only PDF and Word files are allowed.")
        return value
        