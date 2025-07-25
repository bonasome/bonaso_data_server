from rest_framework import serializers
from flags.models import Flag
from profiles.serializers import ProfileListSerializer
from django.utils.timezone import now

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
    
    #auto create logic will bypass this serializer, this is specific for human created_flags
    #business logic is handled by seperate actions (i.e., managing specific perms)
    def validate(self, attrs):
        user = self.context['request'].user

        reason = attrs.get('reason', getattr(self.instance, 'reason', None))
        resolved = attrs.get('resolved', getattr(self.instance, 'resolved', False))
        resolved_reason = attrs.get('resolved_reason', getattr(self.instance, 'resolved_reason', None))
        auto_flagged = attrs.get('auto_flagged', getattr(self.instance, 'auto_flagged', False))

        if not reason and not auto_flagged:
            raise serializers.ValidationError('You must provide a reason for raising a flag.')

        if resolved and not resolved_reason:
            raise serializers.ValidationError('You must provide a reason for resolving a flag.')

        return attrs
        
    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['created_by'] = user
        validated_data['updated_by'] = user
        validated_data['caused_by'] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data['updated_by'] = self.context['request'].user
        if validated_data['resolved'] and not (validated_data['auto_resolved'] or validated_data['resolved_by']):
            validated_data['resolved_by'] = self.context['request'].user
            validated_data.setdefault('resolved_at', now())
        return super().update(instance, validated_data) 
