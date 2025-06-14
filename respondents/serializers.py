from rest_framework import serializers
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, KeyPopulation
from projects.models import Task
from projects.serializers import TaskSerializer
from indicators.models import IndicatorSubcategory

class RespondentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Respondent
        fields = ['id', 'uuid', 'is_anonymous', 'first_name', 'last_name', 'sex', 
                  'village', 'district', 'citizenship', 'comments']

class KPSerializer(serializers.ModelSerializer):
    class Meta:
        model = KeyPopulation
        fields = ['id', 'name']

class RespondentSerializer(serializers.ModelSerializer):
    id_no = serializers.CharField(write_only=True, required=False, allow_blank=True)
    is_pregnant = serializers.SerializerMethodField()
    hiv_status = serializers.SerializerMethodField()
    kp_status = KPSerializer(read_only=True, many=True)
    kp_status_id = serializers.PrimaryKeyRelatedField(queryset=KeyPopulation.objects.all(), write_only=True, many=True, source='kp_status', required=False)
    term_began = serializers.DateField(write_only=True, required=False)
    term_ended = serializers.DateField(write_only=True, required=False)
    date_positive = serializers.DateField(write_only=True, required=False)

    def get_is_pregnant(self, obj):
        return getattr(obj.pregnancy_set, 'is_pregnant', None)
    def get_hiv_status(self, obj):
        return getattr(obj.hivstatus_set, 'hiv_status', None)
    
    class Meta:
        model=Respondent
        fields = [
            'id','id_no', 'uuid', 'is_anonymous', 'first_name', 'last_name', 'sex', 'ward',
            'village', 'district', 'citizenship', 'comments', 'email', 'phone_number', 'dob',
            'age_range', 'is_pregnant', 'term_began', 'term_ended', 'hiv_status', 'date_positive',
            'kp_status', 'kp_status_id'
        ]

class InteractionSerializer(serializers.ModelSerializer):
    respondent = serializers.PrimaryKeyRelatedField(queryset=Respondent.objects.all())
    task = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True)
    task_detail = TaskSerializer(source='task', read_only=True)
    subcategories = serializers.PrimaryKeyRelatedField(many=True, queryset=IndicatorSubcategory.objects.all())
    class Meta:
        model=Interaction
        fields = [
            'id', 'respondent', 'subcategories', 'task', 'task_detail', 'interaction_date', 'numeric_component'
        ]
        