from rest_framework import serializers
from django.db.models import Q
from indicators.models import Indicator, IndicatorSubcategory
from projects.models import Target
from respondents.models import Interaction, HIVStatus, Pregnancy, InteractionSubcategory
from events.models import Event, DemographicCount
from datetime import date
from collections import defaultdict

class IndicatorSubcategorySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    class Meta:
        model = IndicatorSubcategory
        fields = ['id', 'name', 'deprecated']

class IndicatorListSerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    def get_subcategories(self, obj):
        return obj.subcategories.filter(deprecated=False).count()

    class Meta:
        model=Indicator
        fields = ['id', 'code', 'name', 'subcategories']

class PrerequisiteSerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    def get_subcategories(self, obj):
        return obj.subcategories.filter(deprecated=False).count()
    class Meta:
        model = Indicator
        fields = ['id', 'code', 'name', 'subcategories']

class IndicatorSerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    subcategory_data = IndicatorSubcategorySerializer(many=True, write_only=True, required=False)
    required_attribute_names = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )

    prerequisites = PrerequisiteSerializer(read_only=True, many=True)
    prerequisite_id = serializers.PrimaryKeyRelatedField(
        source='prerequisites',
        queryset=Indicator.objects.all(),
        many=True,
        write_only=True,
        required=False, 
        allow_null=True,
    )
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
    match_subcategories_to = serializers.PrimaryKeyRelatedField(
        queryset=Indicator.objects.all(),
        required=False,
        allow_null=True
    )
    
    def get_subcategories(self, obj):
        active_subcats = obj.subcategories.filter(deprecated=False)
        return IndicatorSubcategorySerializer(active_subcats, many=True).data

    
    def get_created_by(self, obj):
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
        fields = ['id', 'name', 'code', 'prerequisites', 'prerequisite_id', 'description', 'subcategories', 'match_subcategories_to',
                  'subcategory_data', 'require_numeric', 'status', 'created_by', 'created_at', 'allow_repeat', 'governs_attribute',
                  'updated_by', 'updated_at', 'required_attribute', 'required_attribute_names', 'indicator_type']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Lazy import to avoid circular dependency
        from respondents.serializers import RespondentAttributeTypeSerializer

        representation['required_attribute'] = RespondentAttributeTypeSerializer(
            instance.required_attribute.all(), many=True
        ).data

        return representation
    
    def validate_prerequisite_id(self, value):
        if self.instance:
            for prereq in value:
                if prereq == self.instance:
                    raise serializers.ValidationError("An indicator cannot be its own prerequisite.")
                if prereq.indicator_type != self.instance.indicator_type:
                    raise serializers.ValidationError("Prerequisites must match the indicator type.")
        return value

    def validate(self, attrs):
        code = attrs.get('code', getattr(self.instance, 'code', None))
        name = attrs.get('name', getattr(self.instance, 'name', None))
        status = attrs.get('status', getattr(self.instance, 'status', None))
        indicator_type = attrs.get('indicator_type', getattr(self.instance, 'indicator_type', None))
        prerequisites = attrs.get('prerequisites', getattr(self.instance, 'prerequisites', None))
        required_attribute = attrs.get('required_attribute_names', getattr(self.instance, 'required_attribute_names', None))
        governs_attribute = attrs.get('governs_attribute', getattr(self.instance, 'governs_attribute', None))
        ind_id = self.instance.id if self.instance else None
        match_subcategories_to = attrs.get('match_subcategories_to', None)
        subcategory_data = attrs.get('subcategory_data', [])
        if not code:
            raise serializers.ValidationError({"code": "Code is required."})
        if not name:
            raise serializers.ValidationError({"name": "Name is required."})
        # Uniqueness check for 'code'
        qs = Indicator.objects.filter(code=code)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            existing = qs.first()
            raise serializers.ValidationError({"code": f"Code already used by indicator {existing.code}: {existing.name}."})
        # Uniqueness check for 'name'
        qs = Indicator.objects.filter(name=name)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            existing = qs.first()
            raise serializers.ValidationError({"name": f"Name already used by indicator {existing.code}: {existing.name}."})
        if prerequisites:
            if hasattr(prerequisites, 'all'):
                prerequisites = list(prerequisites.all())
            for prerequisite in prerequisites:
                if prerequisite.status == 'Deprecated':
                    raise serializers.ValidationError({"prerequisites": "This selected prerequisite indicator has been marked as deprecated, and therefore cannot be used as a prerequiste."})
                if status == 'Active' and prerequisite.status == 'Planned':
                    raise serializers.ValidationError({"prerequisites": "This indicator's prerequisite is not active although this indicator was marked as active. Please set that indicator as active first."})
                if indicator_type != prerequisite.indicator_type:
                    raise serializers.ValidationError({"prerequisites": f"This indicator is marked as type {indicator_type} which does not match the selected prerequisite {prerequisite.indicator_type} ."})
        if ind_id:
            dependencies = Indicator.objects.filter(prerequisites__id = ind_id)
            if dependencies:
                for dep in dependencies:
                    if indicator_type != dep.indicator_type:
                        raise serializers.ValidationError({"indicator type": f"Indicator {dep.name} uses this indicator as a prerequisite. You may not change this indicators type, as it will invalidate that indicator."})
                    if dep.status != 'Deprecated' and status =='Deprecated':
                        raise serializers.ValidationError({"status": f"Indicator {dep.name} uses this indicator as a prerequisite. You must deprecate that indicator first."})
                    elif dep.status == 'Active' and status == 'Planned':
                        raise serializers.ValidationError({"status": f"Indicator {dep.name} is active and uses this indicator as a prerequisite. You must mark that indicator as planned first."})
        if required_attribute and indicator_type != 'Respondent':
            raise serializers.ValidationError({"required_attribute": "For this indicator to have required attributes, its type must be set to 'Respondent'."})
        if governs_attribute and indicator_type != 'Respondent':
            raise serializers.ValidationError({"governs_attribute": "For this indicator to be able to govern attributes, its type must be set to 'Respondent'."})
        if match_subcategories_to and not prerequisites:
            raise serializers.ValidationError({"match_subcategories_to": "Matching subcategories is only allowed for indicators with a prerequisite."})
        if match_subcategories_to and not match_subcategories_to in prerequisites:
            raise serializers.ValidationError({"match_subcategories_to": "Cannot match subcategories with an indicator that has no subcategories."})
        if len(subcategory_data) > 0 and match_subcategories_to:
            prereq_ids = [c.id for c in match_subcategories_to.subcategories.all()]
            child_ids = [c.get('id') for c in subcategory_data]
            if set(prereq_ids) != set(child_ids):
                raise serializers.ValidationError({"match_subcategories_to": "Found conflicting requests to match subcategories and provide unique subcategory values."})
        return attrs
    
    def validate_governs_attribute(self, value):
        if not value:
            return None
        from respondents.models import RespondentAttributeType
        valid_choices = set(choice[0] for choice in RespondentAttributeType.Attributes.choices)
        if value not in valid_choices:
            raise serializers.ValidationError(f"{value} is not a valid attribute.")
        return value

    def validate_required_attribute_names(self, value):
        from respondents.models import RespondentAttributeType
        valid_choices = set(choice[0] for choice in RespondentAttributeType.Attributes.choices)
        for name in value:
            if name not in valid_choices:
                raise serializers.ValidationError(f"{name} is not a valid attribute.")
        return value

    def create(self, validated_data):
        from respondents.models import RespondentAttributeType
        prerequisites = validated_data.pop('prerequisites', [])
        subcategory_data = validated_data.pop('subcategory_data', [])
        required_attribute_names = validated_data.pop('required_attribute_names', [])
        indicator = Indicator.objects.create(**validated_data)
        indicator.prerequisites.set(prerequisites)

        if indicator.match_subcategories_to:
            prereq_subcats = IndicatorSubcategory.objects.filter(indicator=indicator.match_subcategories_to)
            indicator.subcategories.set(prereq_subcats)
        else:
            cleaned_names = [
                name.get('name').replace(',', '').replace(':', '') for name in subcategory_data if name.get('name')
            ]
            subcategories = [
                IndicatorSubcategory.objects.create(name=name, deprecated=False)
                for name in cleaned_names
            ]
            indicator.subcategories.set(subcategories)

        attrs = [
            RespondentAttributeType.objects.get_or_create(name=name)
            for name in required_attribute_names
        ]
        indicator.required_attribute.set(attrs)

        return indicator

    def update(self, instance, validated_data):
        from respondents.models import RespondentAttributeType
        prerequisites = validated_data.pop('prerequisites', None)
        subcategory_data = validated_data.pop('subcategory_data', None)
        required_attribute_names = validated_data.pop('required_attribute_names', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        if prerequisites is not None:
            instance.prerequisites.set(prerequisites)
        if instance.match_subcategories_to:
            prereq_subcats = IndicatorSubcategory.objects.filter(indicator=instance.match_subcategories_to)
            instance.subcategories.set(prereq_subcats)
        elif not instance.match_subcategories_to and subcategory_data is None:
            instance.subcategories.set([])
        else:
            subcategories = []
            if subcategory_data is not None:
                for cat in subcategory_data:
                    deprecated = str(cat.get('deprecated')).strip().lower() in ['true', '1']
                    name = cat.get('name')
                    if not name:
                        raise serializers.ValidationError(f'Subcategory name may not be blank.')
                    name = name.replace(',', '').replace(':', '')
                    existing_id = cat.get('id')
                    #rogue ids should not be happening, and might be a sign of an issue on the front end
                    subcategory = None
                    if existing_id:
                        subcategory = IndicatorSubcategory.objects.filter(id=existing_id).first()
                        if not subcategory:
                            raise serializers.ValidationError(f'Could not find subcategory of id {existing_id}')
                        subcategory.name = name
                        subcategory.deprecated = deprecated
                        subcategory.save()
                    else:
                        if deprecated:
                            raise serializers.ValidationError(f'You are creating and immediately deprecating subcategory "{name}". Please verify this result')
                        subcategory = IndicatorSubcategory.objects.create(name=name, deprecated=deprecated)
                    subcategories.append(subcategory)
                instance.subcategories.set(subcategories)
                children = Indicator.objects.filter(prerequisites=instance, match_subcategories_to=self.instance)
                for child in children:
                    child.subcategories.set(subcategories)

        if required_attribute_names is not None:
            attrs = [
                RespondentAttributeType.objects.get_or_create(name=name)[0]
                for name in required_attribute_names
            ]
            instance.required_attribute.set(attrs)
        return instance

class ChartSerializer(serializers.ModelSerializer):
    interactions = serializers.SerializerMethodField()
    events = serializers.SerializerMethodField()
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
    
    def get_events(self, obj):
        from events.models import CountFlag
        from events.serializers import EventSerializer, DCSerializer
        organization_id = self.context.get('organization_id')
        project_id = self.context.get('project_id')

        events = Event.objects.filter(tasks__indicator=obj, status='Completed').distinct()
        if organization_id:
            events = events.filter(Q(organizations__id=organization_id) | Q(host_id=organization_id))
        if project_id:
            events = events.filter(tasks__project__id=project_id)

        event_ids = {e.id for e in events}
        counts = DemographicCount.objects.filter(event_id__in=event_ids, task__indicator=obj)
        
        flags = CountFlag.objects.filter(count__in=counts, resolved=False)
        flagged_ids = flags.values_list('count_id', flat=True)

        # Group counts by event_id
        counts_by_event = defaultdict(list)
        for count in counts:
            counts_by_event[count.event_id].append(count)

        result = []
        for event in events:
            serialized_event = EventSerializer(event, context=self.context).data
            serialized_counts = DCSerializer(counts_by_event.get(event.id, []), many=True, context=self.context).data
            for count_dict in serialized_counts:
                if count_dict.get('id') in flagged_ids:
                    continue
                subcat_id = count_dict.pop('subcategory')
                if subcat_id:
                    instance = IndicatorSubcategory.objects.get(id=subcat_id)
                    count_dict['subcategory'] = IndicatorSubcategorySerializer(instance, context=self.context).data
            result.append({
                'event': serialized_event,
                'counts': serialized_counts
            })

        return result


    def get_interactions(self, obj):
        from respondents.models import InteractionFlag
        organization_id = self.context.get('organization_id')
        project_id = self.context.get('project_id')
        interactions = Interaction.objects.filter(task__indicator=obj).select_related(
            'respondent', 'task__organization'
        )
        
        if organization_id:
            interactions = interactions.filter(task__organization__id=organization_id)
        if project_id:
            interactions = interactions.filter(task__project__id=project_id)

        flags = InteractionFlag.objects.filter(interaction__in=interactions, resolved=False)
        flagged_ids = flags.values_list('interaction_id', flat=True)

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
            if interaction.id in flagged_ids:
                continue
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
                'subcategories': [{'name': c.subcategory.name, 'numeric_component': c.numeric_component, 'deprecated': c.subcategory.deprecated} for c in subcats],
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
            'id', 'interactions', 'targets', 'name', 'subcategories', 'require_numeric', 'legend', 
            'legend_labels', 'events', 'indicator_type',
        ]