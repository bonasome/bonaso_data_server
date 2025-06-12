from rest_framework import serializers
from organizations.models import Organization

class OrgsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name']