from rest_framework import serializers

from django.contrib.auth import get_user_model
User = get_user_model()

from organizations.serializers import OrganizationListSerializer
from organizations.models import Organization
from profiles.models import FavoriteObject

class ProfileListSerializer(serializers.ModelSerializer):
    '''
    Lightweight serializer used quite a bit for getting created by/updated by
    '''
    display_name = serializers.SerializerMethodField(read_only=True)
    organization = OrganizationListSerializer(read_only=True)

    def get_display_name(self, obj):
        if obj.first_name and obj.last_name:
            return f'{obj.first_name} {obj.last_name}'
        else:
            return f'{obj.username}'
    class Meta:
        model=User
        fields = ['id', 'display_name', 'organization']

class ProfileSerializer(serializers.ModelSerializer):
    '''
    Slightly more inclusive serializer for profile pages.
    '''
    display_name = serializers.SerializerMethodField(read_only=True)
    organization = OrganizationListSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization')

    def get_display_name(self, obj):
        if obj.first_name and obj.last_name:
            return f'{obj.first_name} {obj.last_name}'
        else:
            return f'{obj.username}'
        
    class Meta:
        model=User
        fields = ['id', 'username', 'first_name', 'last_name', 'email','organization', 'display_name',
                  'organization_id', 'role', 'is_active', 'client_organization', 'date_joined', 'last_login']
        read_only_fields = ['id']

    def get_fields(self):
        fields = super().get_fields()
        user = self.context['request'].user

        if user.role != 'admin':
            fields['is_active'].read_only = True
            fields['role'].read_only = True

        return fields

class FavoriteObjectSerializer(serializers.ModelSerializer):
    '''
    Serializer for tracking favorited items.
    '''
    class Meta:
        model = FavoriteObject
        fields = ['id', 'content_type', 'object_id', 'user']