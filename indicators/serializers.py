from rest_framework import serializers
from indicators.models import Indicator, IndicatorSubcategory
from projects.models import Target
from respondents.models import Interaction, HIVStatus, Pregnancy, InteractionSubcategory
from datetime import date

class IndicatorSubcategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorSubcategory
        fields = ['id', 'name']

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
        required_attribute = validated_data.pop('required_attribute', [])
        cleaned_names = [
            name.replace(',', '').replace(':', '') for name in subcategory_names
        ]
        indicator = Indicator.objects.create(**validated_data)
        subcategories = [
            IndicatorSubcategory.objects.get_or_create(name=name)[0]
            for name in cleaned_names
        ]
        indicator.subcategories.set(subcategories)
        return indicator

    def update(self, instance, validated_data):
        subcategory_names = validated_data.pop('subcategory_names', None)
        cleaned_names = [
            name.replace(',', '').replace(':', '') for name in subcategory_names
        ]
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if subcategory_names is not None:
            subcategories = [
                IndicatorSubcategory.objects.get_or_create(name=name)[0]
                for name in cleaned_names
            ]
            instance.subcategories.set(subcategories)
        return instance

class ChartSerializer(serializers.ModelSerializer):
    interactions = serializers.SerializerMethodField()
    targets = serializers.SerializerMethodField()
    subcategories = IndicatorSubcategorySerializer(many=True, read_only=True)
    legend = serializers.SerializerMethodField()
    legend_labels = serializers.SerializerMethodField()
    def get_legend(self, obj):
        legend = ['age_range', 'sex', 'kp_status', 'disability_status', 'citizenship', 'district', 'organization', 'hiv_status', 'pregnant']
        if IndicatorSubcategory.objects.filter(indicator=obj).exists():
            legend.append('subcategories')
        if Target.objects.filter(task__indicator=obj).exists():
            legend.append('targets')
        return legend

    def get_legend_labels(self, obj):
        legend = ['Age Range', 'Sex', 'Key Population Status', 'Disability Status', 'Citizenship', 'District', 'Organization', 'HIV Status', 'Is Pregnant']
        if IndicatorSubcategory.objects.filter(indicator=obj).exists():
            legend.append('Subcategories')
        if Target.objects.filter(task__indicator=obj).exists():
            legend.append('vs. Targets')
        return legend
    
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
            'respondent__kp_status', 'respondent__disability_status'
        )

        respondent_ids = {i.respondent_id for i in interactions}
    
        hiv_statuses = HIVStatus.objects.filter(respondent_id__in=respondent_ids)
        pregnancies = Pregnancy.objects.filter(respondent_id__in=respondent_ids)

        # Group by respondent_id for quick lookup
        hiv_status_by_respondent = {}
        for hs in hiv_statuses:
            if hs and hs.date_positive:
                hiv_status_by_respondent.setdefault(hs.respondent_id, []).append(hs)

        pregnancies_by_respondent = {}
        for p in pregnancies:
            if p and p.term_began:
                pregnancies_by_respondent.setdefault(p.respondent_id, []).append(p)
        result = []
        for interaction in interactions:
            respondent = interaction.respondent
            hiv_status = any(
                hs. date_positive <= interaction.interaction_date
                for hs in hiv_status_by_respondent.get(respondent.id, [])
            )
            # Pregnancy lookup
            pregnancy = any(
                p.term_began <= interaction.interaction_date <= p.term_ended if p.term_ended else date.today()
                for p in pregnancies_by_respondent.get(respondent.id, [])
            )
            subcats = InteractionSubcategory.objects.filter(interaction=interaction)
            result.append({
                'respondent': {
                    'id': interaction.respondent.id,
                    'age_range': interaction.respondent.age_range,
                    'sex': interaction.respondent.sex,
                    'kp_status': [kp.name for kp in interaction.respondent.kp_status.all()],
                    'disability_status': [d.name for d in interaction.respondent.disability_status.all()],
                    'citizenship': interaction.respondent.citizenship == 'Motswana',
                    'district': interaction.respondent.district,
                    'hiv_status': hiv_status,
                    'pregnant': pregnancy,
                },
                'subcategories': [{'name': c.subcategory.name, 'numeric_component': c.numeric_component} for c in subcats],
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
        target_qs = target_qs.select_related('task__organization')
        targets = []
        for t in target_qs:
            percentage = None
            print(t)
            if not t.amount and t.related_to and t.percentage_of_related:
                percentage = Interaction.objects.filter(task = t.related_to, interaction_date__gte = t.start, interaction_date__lte=t.end, flagged=False).count() * (t.percentage_of_related/100)
            targets.append({
                    'id': t.id,
                    'indicator': t.task.indicator.id,
                    'organization': t.task.organization.id,
                    'amount': t.amount if t.amount else percentage or None,
                    'start': t.start,
                    'end': t.end,
                })
        return targets
    class Meta:
        model=Indicator
        fields = [
            'id', 'interactions', 'targets', 'name', 'subcategories', 'require_numeric', 'legend', 'legend_labels'
        ]