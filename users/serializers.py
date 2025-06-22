from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework.exceptions import PermissionDenied

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token['username'] = user.username
        token['role'] = user.role
        token['organization_id'] = user.organization.id if user.organization else None

        return token
    def validate(self, attrs):
        data = super().validate(attrs)
        if not self.user.is_active:
            raise PermissionDenied('Your account has been deactivated.')
        return super().validate(attrs)

class CustomMobileTokenSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token["username"] = user.username
        token["role"] = user.role
        token["organization_id"] = user.organization.id if user.organization else None

        return token