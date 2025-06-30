from rest_framework import serializers
from indicators.models import Indicator, IndicatorSubcategory
from projects.models import Target
from respondents.models import Interaction

class IndicatorSubcategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorSubcategory
        fields = ['name']

class IndicatorListSerializer(serializers.ModelSerializer):
    class Meta:
        model=Indicator
        fields = ['id', 'code', 'name']

class PrerequisiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indicator
        fields = ['id', 'code', 'name']

class IndicatorSerializer(serializers.ModelSerializer):
    subcategories = IndicatorSubcategorySerializer(many=True, read_only=True)
    subcategory_names = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )
    prerequisite = PrerequisiteSerializer(read_only=True)
    prerequisite_id = serializers.PrimaryKeyRelatedField(
        source='prerequisite',
        queryset=Indicator.objects.all(),
        write_only=True,
        required=False, 
        allow_null=True,
    )
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()

    def get_created_by(self, obj):
        print(obj.created_by)
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "first_name": obj.created_by.first_name,
                "last_name": obj.created_by.last_name,
            }

    def get_updated_by(self, obj):
        if obj.updated_by:
            return {
                "id": obj.updated_by.id,
                "username": obj.updated_by.username,
                "first_name": obj.updated_by.first_name,
                "last_name": obj.updated_by.last_name,
            }
        
    class Meta:
        model = Indicator
        fields = ['id', 'name', 'code', 'prerequisite', 'prerequisite_id', 'description', 'subcategories', 
                  'subcategory_names', 'require_numeric', 'status', 'created_by', 'created_at', 
                  'updated_by', 'updated_at']

    def validate(self, attrs):
        code = attrs.get('code', getattr(self.instance, 'code', None))
        name = attrs.get('name', getattr(self.instance, 'name', None))
        if not code:
            raise serializers.ValidationError({"code": "Code is required."})
        if not name:
            raise serializers.ValidationError({"name": "Name is required."})
        # Uniqueness check for 'code'
        qs = Indicator.objects.filter(code=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"code": "Code must be unique."})
        # Uniqueness check for 'name'
        qs = Indicator.objects.filter(name=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": "Name must be unique."})
        return attrs
    
    def create(self, validated_data):
        subcategory_names = validated_data.pop('subcategory_names', [])
        indicator = Indicator.objects.create(**validated_data)
        subcategories = [
            IndicatorSubcategory.objects.get_or_create(name=name)[0]
            for name in subcategory_names
        ]
        indicator.subcategories.set(subcategories)
        return indicator

    def update(self, instance, validated_data):
        subcategory_names = validated_data.pop('subcategory_names', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if subcategory_names is not None:
            subcategories = [
                IndicatorSubcategory.objects.get_or_create(name=name)[0]
                for name in subcategory_names
            ]
            instance.subcategories.set(subcategories)
        return instance

class ChartSerializer(serializers.ModelSerializer):
    interactions = serializers.SerializerMethodField()
    targets = serializers.SerializerMethodField()
    subcategories = IndicatorSubcategorySerializer(many=True, read_only=True)
    
    def get_interactions(self, obj):
        organization_id = self.context.get('organization_id')
        project_id = self.context.get('project_id')
        interactions = Interaction.objects.filter(task__indicator=obj).select_related(
            'respondent', 'task__organization'
        )
        if organization_id:
            interactions = interactions.filter(task__organization__id=organization_id)
        if project_id:
            interactions = interactions.filter(task__project__id=project_id)
        interactions.prefetch_related(
            'respondent__kp_status', 'respondent__disability_status', 'subcategories'
        )
        result = []
        for interaction in interactions:
            result.append({
                'respondent': {
                    'id': interaction.respondent.id,
                    'age_range': interaction.respondent.age_range,
                    'sex': interaction.respondent.sex,
                    'kp_status': [kp.name for kp in interaction.respondent.kp_status.all()],
                    'disability_status': [d.name for d in interaction.respondent.disability_status.all()],
                    'citizenship': interaction.respondent.citizenship == 'Motswana',
                    'district': interaction.respondent.district
                },
                'subcategories': [c.name for c in interaction.subcategories.all()],
                'interaction_date': interaction.interaction_date,
                'numeric_component': interaction.numeric_component,
                'organization': {
                    'id': interaction.task.organization.id,
                    'name': interaction.task.organization.name,
                }
            })
        return result   
    def get_targets(self, obj):
        target_qs = Target.objects.filter(task__indicator=obj)
        organization_id = self.context.get('organization_id')
        project_id = self.context.get('project_id')
        if organization_id:
            target_qs = target_qs.filter(task__organization__id=organization_id)
        if project_id:
            target_qs = target_qs.filter(task__project__id=project_id)
        target_qs.select_related('task__organization')
        return [
            {
                'id': t.id,
                'indicator': t.task.indicator.id,
                'organization': t.task.organization.id,
                'amount': t.amount,
                'start': t.start,
                'end': t.end,
            }
            for t in target_qs
        ]
    class Meta:
        model=Indicator
        fields = [
            'id', 'interactions', 'targets', 'name', 'subcategories', 'require_numeric'
        ]