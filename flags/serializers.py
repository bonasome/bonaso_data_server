from rest_framework import serializers

from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now

from flags.models import Flag
from profiles.serializers import ProfileListSerializer


class FlagSerializer(serializers.ModelSerializer):
    '''
    Serializer for viewing flags (create/resolve is handled through custom actions)
    '''
    created_by = ProfileListSerializer(read_only=True)
    resolved_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    caused_by = ProfileListSerializer(read_only=True)
    target = serializers.SerializerMethodField(read_only=True)
    model_string = serializers.SerializerMethodField(read_only=True)

    def get_model_string(self, obj):
        #get app/model as a string so the frontend can categorize
        content_type = ContentType.objects.get(id=obj.content_type.id)
        return f"{content_type.app_label}.{content_type.model}"
    
    def get_target(self, obj):
        '''
        Get the object type and some information that is required for filtering/linking at the frontend. 
        '''
        try:
            ct = ContentType.objects
            self.ct_respondent = ct.get(app_label='respondents', model='respondent')
            self.ct_interaction = ct.get(app_label='respondents', model='interaction')
            self.ct_count = ct.get(app_label='aggregates', model='aggregatecount')
            self.ct_social_post = ct.get(app_label='social', model='socialmediapost')
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

            elif obj.content_type == self.ct_count:
                return {
                    'id': obj.target.id,
                    'parent': obj.target.group_id if obj.target.group else None,
                    'project': None,
                    'organization': obj.target.organization_id if obj.target.organization else None,
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
