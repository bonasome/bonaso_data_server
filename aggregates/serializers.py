from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from django.db import transaction
from django.db.models import Q
from datetime import datetime, date

from profiles.serializers import ProfileListSerializer
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from projects.models import ProjectOrganization,Project, Task
from projects.serializers import ProjectListSerializer
from flags.serializers import FlagSerializer
from indicators.models import Indicator, Option, LogicCondition, LogicGroup, Assessment
from indicators.serializers import IndicatorSerializer, OptionSerializer
from aggregates.models import AggregateCount, AggregateGroup
from flags.utils import create_flag, resolve_flag
from flags.models import Flag
from flags.serializers import FlagSerializer

class AggregatGroupListSerializer(serializers.ModelSerializer):
    organization = OrganizationListSerializer(read_only=True)
    project = ProjectListSerializer(read_only=True)
    indicator = IndicatorSerializer(read_only=True)

    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)

    class Meta:
        model = AggregateGroup
        fields = [
            'id', 'organization', 'indicator', 'project',
            'start', 'end', 'created_by', 'created_at', 'updated_by', 'updated_at'
        ]

class AggregateCountSerializer(serializers.ModelSerializer):
    option = OptionSerializer(read_only=True)
    option_id = serializers.PrimaryKeyRelatedField(queryset=Option.objects.all(), write_only=True, source='option', required=False, allow_null=True)
    flags = FlagSerializer(read_only=True, many=True)
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
            'flags',
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
        elif indicator.type not in [Indicator.Type.MULTI, Indicator.Type.SINGLE]:
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
        assessments = Assessment.objects.filter(id=indicator.assessment_id).values_list('id', flat=True)
        if not Task.objects.filter(Q(organization=org, project=proj, indicator=indicator) | Q(organization=org, project=proj, assessment_id__in=assessments)):
            raise serializers.ValidationError('There is no task associated with this indicator for this project/organiation.')
        #check for overlaps
        start =attrs.get('start')
        end=attrs.get('end')

        if start > end:
            raise serializers.ValidationError("Start must be before the end.")
        if start > date.today():
            raise serializers.ValidationError('Cannot record aggregates for the future.')
        
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
    
    def __check_logic(self, indicator, organization, start, end, count, user, visited=None):
        if visited is None:
            visited = set()
        
        key = (indicator.id, count.id)
        if key in visited:
            return
        visited.add(key)

        flags = count.flags.filter(auto_flagged=True)
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
                'group__start__lt': end,
                'group__end__gt': start,
                'group__indicator': prereq,
                'group__organization': organization,
            }
            for field in ['sex', 'age_range', 'kp_type', 'disability_type', 'hiv_status', 'pregnancy', 'district', 'citizenship', 'attribute_type']:
                value = getattr(count, field)
                if value is not None:
                    filters[field] = value
            if count.option_id is not None:
                filters['option_id'] = count.option_id

            find_count = AggregateCount.objects.filter(**filters).first()

            # Logic: NONE / False condition
            if condition.condition_type == LogicCondition.ExtraChoices.NONE or condition.value_boolean is False:
                '''
                Skip "negative" logic (i.e., false, nothing selected), since aggregate formats only 
                collect "positive data"
                '''
                continue
            else:
                # Logic: prereq must exist and be >= this value
                msg = f'Indicator "{indicator.name}" requires a corresponding count for {prereq.name}.'
                if not find_count:
                    create_flag(instance=count, reason=msg, caused_by=user, reason_type=Flag.FlagReason.MPRE)
                else:
                    resolve_flag(flags, msg)
                if find_count:
                    msg = f'Value for this count may not be higher than the corresponding value from {prereq.name}.'
                    if val is not None and (find_count.value is None or val > find_count.value):
                        create_flag(instance=count, reason=msg, caused_by=user, reason_type=Flag.FlagReason.MPRE)
                    else:
                        resolve_flag(flags, msg)

        # Check downstream counts recursively
        self.__check_downstream(indicator=indicator, organization=organization, start=start, end=end, count=count, user=user, visited=visited)


    def __check_downstream(self, indicator, organization, start, end, count, user, visited):
        # find all counts overlapping this range
        filters = {
            'group__start__lt': end,
            'group__end__gt': start,
            'group__organization': organization,
        }
        potential_downstream = AggregateCount.objects.filter(**filters)
        for c in potential_downstream:
            ds_ind = c.group.indicator
            conditions = LogicCondition.objects.filter(group__indicator=ds_ind, source_indicator=indicator)
            if conditions.exists():
                self.__check_logic(indicator=ds_ind, organization=organization, start=start, end=end, count=c, user=user, visited=visited)

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
            visited = set()
            for count in saved_instances:
                self.__check_logic(indicator=group.indicator, organization=group.organization, start=group.start, end=group.end,count= count, user=user, visited=visited)
                self.__check_downstream(indicator=group.indicator, organization=group.organization, start=group.start, end=group.end, count=count, user=user, visited=visited)
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
            visited = set()
            for count in saved_instances:
                self.__check_logic(indicator=instance.indicator, organization=instance.organization, start=instance.start, end=instance.end, count=count, user=user, visited=visited)
                self.__check_downstream(indicator=instance.indicator, organization=instance.organization, start=instance.start, end=instance.end, count=count, user=user, visited=visited)
        return instance