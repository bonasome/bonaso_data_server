from rest_framework import serializers

from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
User = get_user_model()

from organizations.serializers import OrganizationListSerializer
from organizations.models import Organization
from profiles.models import FavoriteObject
from projects.models import Client
class ProfileListSerializer(serializers.ModelSerializer):
    '''
    Lightweight serializer used for index views and for getting created by/updated by
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
    Slightly more inclusive serializer for profile pages. Also used for editing fields
    '''
    display_name = serializers.SerializerMethodField(read_only=True)
    organization = OrganizationListSerializer(read_only=True)
    client_organization =serializers.SerializerMethodField(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization', required=False, allow_null=True)
    client_id = serializers.PrimaryKeyRelatedField(queryset=Client.objects.all(), write_only=True, source='client_organization', required=False, allow_null=True)
    
    def get_client_organization(self, obj):
        if obj.client_organization:
            return {
                'id': obj.client_organization.id,
                'name': obj.client_organization.name
            }
        else:
            return None
    def get_display_name(self, obj):
        if obj.first_name and obj.last_name:
            return f'{obj.first_name} {obj.last_name}'
        else:
            return f'{obj.username}'
        
    class Meta:
        model=User
        fields = ['id', 'username', 'first_name', 'last_name', 'email','organization', 'display_name', 'client_id',
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
    display_name = serializers.SerializerMethodField()
    model_string = serializers.SerializerMethodField()
    def get_display_name(self, obj):
        return str(obj.target)
    def get_model_string(self, obj):
        content_type = ContentType.objects.get(id=obj.content_type.id)
        return f"{content_type.app_label}.{content_type.model}"
    class Meta:
        model = FavoriteObject
        fields = ['id', 'content_type', 'object_id', 'user', 'display_name', 'model_string']