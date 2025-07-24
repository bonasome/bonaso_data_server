from rest_framework import serializers
from organizations.models import Organization

class OrganizationListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name']

class OrganizationSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()

    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "first_name": obj.created_by.first_name,
                "last_name": obj.created_by.last_name,
            }

    def get_updated_by(self, obj):
        if obj.updated_by:
            return {
                "id": obj.updated_by.id,
                "username": obj.updated_by.username,
                "first_name": obj.updated_by.first_name,
                "last_name": obj.updated_by.last_name,
            }
        
    
    class Meta:
        model = Organization
        fields = ['id', 'name', 'full_name', 'office_address', 
                  'office_phone', 'office_email', 'executive_director', 'ed_phone', 'ed_email', 
                  'created_by', 'created_at', 'updated_by', 'updated_at'
                  ]
        
    def validate(self, attrs):
        user = self.context['request'].user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)


        if role not in ['meofficer', 'manager', 'admin']:
            raise serializers.ValidationError(
                'You do not have permission to perform this action.'
            )

        return attrs
