from rest_framework import serializers

from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now

from flags.models import Flag
from profiles.serializers import ProfileListSerializer


class FlagSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    resolved_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    caused_by = ProfileListSerializer(read_only=True)
    target = serializers.SerializerMethodField(read_only=True)
    model_string = serializers.SerializerMethodField(read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # preload content types once
        try:
            ct = ContentType.objects
            self.ct_respondent = ct.get(app_label='respondents', model='respondent')
            self.ct_interaction = ct.get(app_label='respondents', model='interaction')
            self.ct_demo_count = ct.get(app_label='events', model='demographiccount')
            self.ct_social_post = ct.get(app_label='social', model='socialmediapost')
        except Exception:
            self.ct_respondent = None
    def get_model_string(self, obj):
        content_type = ContentType.objects.get(id=obj.content_type.id)
        return f"{content_type.app_label}.{content_type.model}"
    
    def get_target(self, obj):
        try:
            if obj.content_type == self.ct_respondent:
                return {
                    'id': obj.target.id,
                    'parent': None,
                    'project': None,
                    'organization': None,
                    'display': str(obj.target)
                }

            elif obj.content_type == self.ct_interaction:
                return {
                    'id': obj.target.id,
                    'parent': obj.target.respondent.id if obj.target.respondent else None,
                    'project': obj.target.task.project_id if obj.target.task else None,
                    'organization': obj.target.task.organization_id if obj.target.task else None,
                    'display': str(obj.target)
                }

            elif obj.content_type == self.ct_demo_count:
                return {
                    'id': obj.target.id,
                    'parent': obj.target.event_id if obj.target.event else None,
                    'project': obj.target.task.project_id if obj.target.task else None,
                    'organization': obj.target.task.organization_id if obj.target.task else None,
                    'display': str(obj.target)
                }

            elif obj.content_type == self.ct_social_post:
                first_task = obj.target.tasks.first()
                return {
                    'id': obj.target.id,
                    'project': first_task.project_id if first_task else None,
                    'organization': first_task.organization_id if first_task else None,
                    'display': str(obj.target)
                }

        except Exception as e:
            print('Received unexpected model for flag ', obj.id)
            return None
        return None
    
    class Meta:
        model=Flag
        fields = [
            'id', 'content_type', 'object_id', 'target', 'reason_type', 'reason', 'auto_flagged', 'created_by',
            'created_at', 'resolved', 'auto_resolved', 'resolved_reason', 'resolved_by', 'resolved_at', 'updated_at',
            'updated_by', 'caused_by', 'model_string'
        ]
