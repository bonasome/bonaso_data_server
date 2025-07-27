from rest_framework import serializers

from django.utils.timezone import now

from flags.models import Flag
from profiles.serializers import ProfileListSerializer


class FlagSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    resolved_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    caused_by = ProfileListSerializer(read_only=True)
    target = serializers.SerializerMethodField(read_only=True)

    def get_target(self, obj):
        return str(obj.target)

    class Meta:
        model=Flag
        fields = [
            'id', 'content_type', 'object_id', 'target', 'reason_type', 'reason', 'auto_flagged', 'created_by',
            'created_at', 'resolved', 'auto_resolved', 'resolved_reason', 'resolved_by', 'resolved_at', 'updated_at',
            'updated_by', 'caused_by'
        ]
