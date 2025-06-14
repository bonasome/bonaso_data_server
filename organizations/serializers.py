from rest_framework import serializers
from organizations.models import Organization

class ParentOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name']

class OrganizationListSerializer(serializers.ModelSerializer):
    parent_organization = ParentOrganizationSerializer(read_only=True)
    class Meta:
        model = Organization
        fields = ['id', 'name', 'parent_organization']

class OrganizationSerializer(serializers.ModelSerializer):
    parent_organization = ParentOrganizationSerializer(read_only=True)
    parent_organization_id = serializers.PrimaryKeyRelatedField(
        source='parent_organization',
        queryset=Organization.objects.all(),
        write_only=True,
        required=False
    )
    class Meta:
        model = Organization
        fields = ['id', 'name', 'parent_organization', 'parent_organization_id', 'office_address', 
                  'office_phone', 'office_email', 'executive_director', 'ed_phone', 'ed_email', ]
        
    def validate(self, attrs):
        user = self.context['request'].user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)

        parent_org = attrs.get('parent_organization', getattr(self.instance, 'parent_organization', None))

        if role != 'admin':
            if role not in ['meofficer', 'manager']:
                raise serializers.ValidationError(
                    'You do not have permission to perform this action.'
                )
            if org is None:
                raise serializers.ValidationError('You are not assigned to an organization.')
            if parent_org is None or parent_org != org:
                raise serializers.ValidationError(
                    'You may only create an organization that is a direct child of your organization.'
                )

        return attrs