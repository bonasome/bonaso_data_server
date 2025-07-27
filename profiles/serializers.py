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
    organization = OrganizationListSerializer(read_only=True)
    class Meta:
        model=User
        fields = ['id', 'first_name', 'last_name', 'organization']

class ProfileSerializer(serializers.ModelSerializer):
    '''
    Slightly more inclusive serializer for profile pages.
    '''
    organization_detail = OrganizationListSerializer(source='organization', read_only=True)
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True)

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

class FavoriteObjectSerializer(serializers.ModelSerializer):
    '''
    Serializer for tracking favorited items.
    '''
    class Meta:
        model = FavoriteObject
        fields = ['id', 'content_type', 'object_id', 'user']