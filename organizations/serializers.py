from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from organizations.models import Organization

class OrganizationListSerializer(serializers.ModelSerializer):
    '''
    List serializer for index view or use in other serializers
    '''
    class Meta:
        model = Organization
        fields = ['id', 'name']

class OrganizationSerializer(serializers.ModelSerializer):
    '''
    More detailed view for detail page.
    '''
    from profiles.serializers import ProfileListSerializer
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
          
    class Meta:
        model = Organization
        fields = ['id', 'name', 'full_name', 'office_address', 'description',
                  'office_phone', 'office_email', 'executive_director', 'ed_phone', 'ed_email', 
                  'created_by', 'created_at', 'updated_by', 'updated_at'
                  ]
        
    def validate(self, attrs):
        '''
        Only real rules are lower roles can't create and names gotta be unique.
        '''
        user = self.context['request'].user
        role = getattr(user, 'role', None)

        if role not in ['meofficer', 'manager', 'admin']:
            raise PermissionDenied('You do not have permission to perform this action.')
        name = attrs.get('name', None)
        if not name:
            raise serializers.ValidationError('Name is required.')
        if Organization.objects.filter(name=name).exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError('Name is already in use. Please check if this organization is already in the system.')
        return attrs
