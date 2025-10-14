from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from django.db import transaction
from datetime import date

from profiles.serializers import ProfileListSerializer
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from projects.models import ProjectOrganization,Project
from projects.serializers import ProjectListSerializer
from flags.serializers import FlagSerializer
from indicators.models import Indicator, Option, LogicCondition, LogicGroup
from indicators.serializers import IndicatorSerializer, OptionSerializer
from aggregates.models import AggregateCount, AggregateGroup
from flags.utils import create_flag
from flags.models import Flag
class AggregateCountSerializer(serializers.ModelSerializer):
    option = OptionSerializer(read_only=True)
    option_id = serializers.PrimaryKeyRelatedField(queryset=Option.objects.all(), write_only=True, source='option')
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)

    class Meta:
        model = AggregateCount
        fields = [
            'id',
            'option',
            'option_id',
            'sex',
            'age_range',
            'citizenship',
            'hiv_status',
            'district',
            'pregnancy',
            'disability_type',
            'kp_type',
            'attribute_type',
            'value',  
            'created_by', 
            'updated_by', 
            'created_at',
            'updated_at',
        ]
       
    
class AggregatGroupSerializer(serializers.ModelSerializer):
    organization = OrganizationListSerializer(read_only=True)
    project = ProjectListSerializer(read_only=True)
    indicator = IndicatorSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization')
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, source='project')
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), write_only=True, source='indicator')
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    counts_data = AggregateCountSerializer(write_only=True, many=True, required=True)

    counts = serializers.SerializerMethodField()
    def get_counts(self, obj):
        counts = AggregateCount.objects.filter(group=obj)
        return AggregateCountSerializer(counts, many=True).data

    class Meta:
        model = AggregateGroup
        fields = [
            'id', 'organization', 'indicator', 'project', 'organization_id', 'indicator_id', 'project_id',
            'start', 'end', 'created_by', 'created_at', 'updated_by', 'updated_at', 'counts', 'counts_data'
        ]
        

    def __validate_row(self, indicator, data):
        option = data.get('option')
        if indicator.type in [Indicator.Type.MULTI, Indicator.Type.SINGLE] and not option:
            raise serializers.ValidationError("Option is required for this indicator type.")
        elif option and not indicator.type in [Indicator.Type.MULTI, Indicator.Type.SINGLE]:
            # For all other indicator types, option must NOT be provided
            if option:
                raise serializers.ValidationError(
                    f"Option should not be provided for indicator type '{indicator.type}'."
                )

        for field, valid_values in AggregateCount.DEMOGRAPHIC_VALIDATORS.items():
            value = data.get(field)
            if value and value not in valid_values:
                raise serializers.ValidationError({
                    field: f"'{value}' is not a valid choice for {field}."
                })

        return data

    def validate(self, attrs):
        user = self.context.get('request').user if self.context.get('request') else None
        if user.role not in ['admin', 'meofficer', 'manager']:
            raise PermissionDenied('You do not have permission to perform this action.')
        
        indicator = attrs.get('indicator')
        org = attrs.get('organization')
        proj = attrs.get('project')
        if user.role != 'admin':
            is_own_org = org == user.organization
            is_child_org = ProjectOrganization.objects.filter(
                    parent_organization=user.organization,
                    organization=org,
                    project=proj,
                ).exists()

            if not (is_own_org or is_child_org):
                raise PermissionDenied("You do not have permission to create aggregates not related to your organization.")
         #check for overlaps
        start =attrs.get('start')
        end=attrs.get('end')
        if start and end:
            overlaps = AggregateGroup.objects.filter(
                indicator=indicator,
                project=proj,
                organization=org,
                start__lte=end,
                end__gte=start,
            )
            if self.instance:
                overlaps = overlaps.exclude(pk=self.instance.pk)
        if overlaps.exists():
            raise serializers.ValidationError("This aggregate overlaps with an existing aggregate in the same time period.")
        
        # ✅ Boolean or select indicators should map to an option
        if indicator.category in [Indicator.Category.SOCIAL, Indicator.Category.EVENTS, Indicator.Category.ORGS]: #these should be linked to another object via a task
            raise serializers.ValidationError('Aggregates are not allowed for this indicator category.')
        if indicator.type in [Indicator.Type.TEXT]:
            raise serializers.ValidationError("Aggregates not allowed for this indicator type.")
        if not indicator.allow_aggregate:
            raise serializers.ValidationError("Aggregates not allowed for this indicator.")
        
        counts = attrs.get('counts_data', [])
        breakdown_keys_set = None

        for row in counts:
            self.__validate_row(indicator, row)
            print(row)
            row_keys = set(k for k, v in row.items() if k in AggregateCount.DEMOGRAPHIC_VALIDATORS or k == 'option' and v is not None)
            print(row_keys)
            if breakdown_keys_set is None:
                breakdown_keys_set = row_keys
            elif row_keys != breakdown_keys_set:
                raise serializers.ValidationError(
                    f"Inconsistent breakdowns in counts. "
                    f"All rows must use the same demographic keys: {breakdown_keys_set} vs {row_keys}"
                )
        seen_combinations = set()
        for row in counts:
            # Build a tuple of the values for the breakdown keys
            combination = tuple(row.get(k) for k in breakdown_keys_set)
            if combination in seen_combinations:
                raise serializers.ValidationError(
                    f"Duplicate demographic combination found: {dict(zip(breakdown_keys_set, combination))}"
                )
            seen_combinations.add(combination)
            
        return attrs
    
    def __check_logic(self, indicator, organization, start, end, count, user):
        logic_group = LogicGroup.objects.filter(indicator=indicator).first()
        if not logic_group:
            return
        conditions = LogicCondition.objects.filter(group=logic_group, source_type=LogicCondition.SourceType.ASS)
        if not conditions.exists():
            return
        val = count.value
        for condition in conditions.all():
            prereq = condition.source_indicator
            filters = {
                'group__start__gte': start,
                'group__end__lte': end,
                'group__indicator': prereq,
                'group__organization': organization,
            }
            # dynamically add demographic fields
            for field in ['sex', 'age_range', 'kp_type', 'disability_type', 'hiv_status', 'pregnancy', 'district', 'citizenship', 'attribute_type']:
                value = getattr(count, field)
                if value is not None:
                    filters[field] = value
            if count.option_id is not None:
                filters['option_id'] = count.option_id
            find_count = AggregateCount.objects.filter(**filters).first()
            '''
            In an assessment, this prereq would not be visible if this was being answered
            therefore, the prereq value should either not exist at all or be less than the value for this
            to simulate a series of assessments being taken where the prereq has no value while this has value
            '''
            if condition.condition_type == LogicCondition.ExtraChoices.NONE or condition.value_boolean == False:
                # if the prereq should not be answered for this question to be visible, but its count is greater than this one,
                # that implies that there was a logical error somehwere
                if find_count and find_count.value is not None and find_count.value > val:
                    msg = f'Indicator "{indicator.name}" requires that a corresponding count for {prereq.name} be less than this count.'
                    create_flag(count, msg, user, Flag.FlagReason.MPRE)
            else:
                '''
                Otherwise, the prereq count must have been selected in some capacity (be true, have a number 
                inputed, or have one or more options selected), and therefore this value should never be more
                than the value inputted for the corresponding prereq row
                '''
                if not find_count:
                    msg = f'Indicator "{indicator.name}" requires a corresponding count for {prereq.name}.'
                    create_flag(count, msg, user, Flag.FlagReason.MPRE)
                elif find_count.value is None or val > find_count.value:
                    msg = f'Value for this count may not be higher than the corresponding value from {prereq.name}.'
                    create_flag(count, msg, user, Flag.FlagReason.MPRE)

    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        rows = validated_data.pop('counts_data')
        with transaction.atomic():
            group = AggregateGroup.objects.create(**validated_data)
            group.created_by = user
            group.save()
            instances = [
                AggregateCount(group=group, created_by=user, **row)
                for row in rows
            ]
            saved_instances = AggregateCount.objects.bulk_create(instances)
            for count in saved_instances:
                self.__check_logic(group.indicator, group.organization, group.start, group.end, count, user)
        return group
    
    def update(self, instance, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        rows = validated_data.pop('counts_data')
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.updated_by = user
            instance.save()
            AggregateCount.objects.filter(group=instance).delete()
            instances = [
                AggregateCount(group=instance, created_by=user, **row)
                for row in rows
            ]
            saved_instances = AggregateCount.objects.bulk_create(instances)
            for count in saved_instances:
                self.__check_logic(instance.indicator, instance.organization, instance.start, instance.end, count, user)
        return instance