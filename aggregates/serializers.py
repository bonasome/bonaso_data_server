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

class AggregateGroupListSerializer(serializers.ModelSerializer):
    '''
    Basic list serializer that pulls high level information about an aggregate group for 
    list views. 
    '''
    organization = OrganizationListSerializer(read_only=True)
    project = ProjectListSerializer(read_only=True)
    indicator = IndicatorSerializer(read_only=True)

    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj):
        return str(obj)
    
    class Meta:
        model = AggregateGroup
        fields = [
            'id', 'organization', 'indicator', 'project', 'name', 'display_name',
            'start', 'end', 'created_by', 'created_at', 'updated_by', 'updated_at'
        ]

class AggregateCountSerializer(serializers.ModelSerializer):
    '''
    Helper serializer that pulls information about a specific count.
    '''
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
            'unique_only',
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
       
    
class AggregateGroupSerializer(serializers.ModelSerializer):
    '''
    Full group serializer that pulls aggregate group information as well as related counts. Also 
    used to create/edit aggregate groups.
    '''
    organization = OrganizationListSerializer(read_only=True)
    project = ProjectListSerializer(read_only=True)
    indicator = IndicatorSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization')
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, source='project')
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), write_only=True, source='indicator')
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    counts_data = AggregateCountSerializer(write_only=True, many=True, required=True)
    parent_organization = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()

    def get_counts(self, obj):
        #fetch related counts
        counts = AggregateCount.objects.filter(group=obj)
        return AggregateCountSerializer(counts, many=True).data

    def get_parent_organization(self, obj):
        org_link =  ProjectOrganization.objects.filter(project=obj.project, organization=obj.organization).first()
        return org_link.parent_organization.id if org_link and org_link.parent_organization else None
    
    def get_display_name(self, obj):
        return str(obj)
    class Meta:
        model = AggregateGroup
        fields = [
            'id', 'organization', 'indicator', 'project', 'organization_id', 'indicator_id', 'project_id',
            'start', 'end', 'created_by', 'created_at', 'updated_by', 'updated_at', 'counts', 'counts_data',
            'parent_organization', 'comments', 'name', 'display_name',
        ]
        
    #validate a specific count
    def __validate_row(self, indicator, data):
        #if it has an option, make sure its valid
        option = data.get('option')
        if indicator.type == Indicator.Type.MULTI:
            #make sure that multiselects are sending an aggregated deduplication field for unique only
            if not option and not data.get('unique_only'):
                raise serializers.ValidationError("Option or total flag is required for this indicator type.")
        #make sure option is sent for these types
        if indicator.type in [Indicator.Type.SINGLE, Indicator.Type.MULTINT] and not option:
            raise serializers.ValidationError("Option is required for this indicator type.")
        #and not other types
        elif indicator.type not in [Indicator.Type.MULTI, Indicator.Type.SINGLE, Indicator.Type.MULTINT]:
            # For all other indicator types, option must NOT be provided
            if option:
                raise serializers.ValidationError(
                    f"Option should not be provided for indicator type '{indicator.type}'."
                )
        #make sure that for the demographic fields, a valid value is provided
        for field, valid_values in AggregateCount.DEMOGRAPHIC_VALIDATORS.items():
            value = data.get(field)
            if value and value not in valid_values:
                raise serializers.ValidationError({
                    field: f"'{value}' is not a valid choice for {field}."
                })

        return data

    def validate(self, attrs):
        #check perms
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
       
       #make the indicator/org/project combo exists
        assessments = Assessment.objects.filter(id=indicator.assessment_id).values_list('id', flat=True)
        if not Task.objects.filter(Q(organization=org, project=proj, indicator=indicator) | Q(organization=org, project=proj, assessment_id__in=assessments)):
            raise serializers.ValidationError('There is no task associated with this indicator for this project/organiation.')
        
        #check for overlaps and validate the dates aren't weird
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
        
        # dissallow aggreagates for these categories/types where it doesn't make sense
        if indicator.category in [Indicator.Category.SOCIAL, Indicator.Category.EVENTS, Indicator.Category.ORGS]: #these should be linked to another object via a task
            raise serializers.ValidationError('Aggregates are not allowed for this indicator category.')
        if indicator.type in [Indicator.Type.TEXT]:
            raise serializers.ValidationError("Aggregates not allowed for this indicator type.")
        if not indicator.allow_aggregate:
            raise serializers.ValidationError("Aggregates not allowed for this indicator.")

        #make sure that each count has the same "breakdown" categories (so they can theoretically fit on the same table)
        #Also make sure no "dupliocates" are sent (i.e., 2 females, 18_24, optionA)
        counts = attrs.get('counts_data', [])
        breakdown_keys_set = None

        for row in counts:
            self.__validate_row(indicator, row)
            if row.get('unique_only') and indicator.type == Indicator.Type.MULTI:
                # Unique total row: ignore 'option', use a marker
                row_keys = set(k for k in row.keys() if k in AggregateCount.DEMOGRAPHIC_VALIDATORS)
                row_keys.add('option')  # simulate option selection
            else:
                # Normal option row
                row_keys = set(k for k, v in row.items() if k in AggregateCount.DEMOGRAPHIC_VALIDATORS or (k == 'option' and v is not None))
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
        #validate that total values are present are the option values are not greater than the total/unique value
        if indicator.type == Indicator.Type.MULTI:
            exclude_keys = {'option', 'value', 'unique_only'}
            
            for row in counts:
                val = row.get('value')
                option = row.get('option')
                unique_only = row.get('unique_only', False)

                # Skip total rows (we only validate option rows against totals)
                if unique_only or option is None:
                    continue

                # Ignore empty/zero values safely
                if not val or str(val).strip() == '0':
                    continue

                # Find the corresponding "total" row with same breakdown keys
                target_subset = {k: v for k, v in row.items() if k not in exclude_keys}
                total_match = next(
                    (
                        r for r in counts
                        if not r.get('option')  # total row has no option
                        and r.get('unique_only', True)  # must be marked as total
                        and all(r.get(k) == v for k, v in target_subset.items())
                    ),
                    None,
                )

                if not total_match:
                    raise serializers.ValidationError(
                        f'No total row found for option {option.name if hasattr(option, "name") else option}.'
                    )

                total_val = total_match.get('value') or 0
                if float(val) > float(total_val):
                    raise serializers.ValidationError(
                        f'Count for option {option.name if hasattr(option, "name") else option} '
                        f'({val}) cannot be higher than total ({total_val}).'
                    )

        return attrs

    def __make_breakdown_key(self, indicator_id, count, indicator_type=None):
        base_fields = ['sex', 'age_range', 'kp_type', 'disability_type', 
                    'hiv_status', 'pregnancy', 'district', 
                    'citizenship', 'attribute_type']

        if indicator_type in [Indicator.Type.SINGLE, Indicator.Type.MULTINT]:
            base_fields.append('option')
        elif indicator_type == Indicator.Type.MULTI:
            base_fields.extend(['option', 'unique_only'])

        return (indicator_id, tuple(getattr(count, f, None) for f in base_fields))

    def __check_logic(self, indicator, count, user, related, conditions):
        for condition in conditions:
            prereq = condition.source_indicator
            lookup_key = self.__make_breakdown_key(prereq.id, count, prereq.type)
            #find a count that overlaps with this one, has the prerequisite indicator, and belongs to the same org
            find_count = related.get(lookup_key)

            val = count.value
            # Logic: NONE / False condition
            if condition.condition_type == LogicCondition.ExtraChoices.NONE or condition.value_boolean is False:
                '''
                Skip "negative" logic (i.e., false, nothing selected), since aggregate formats only 
                collect "positive data"
                '''
                continue
            else:
                # Logic: prereq must exist and be >= this value
                msg = f'Count for Indicator "{indicator.name}" is missing prerequsite counts.'
                if not find_count:
                    create_flag(instance=count, reason=msg, caused_by=user, reason_type=Flag.FlagReason.MPRE)
                else:
                    resolve_flag(count.flags, msg)
                if find_count:
                    msg = f'Value for this count may not be higher than the corresponding value from {prereq.name}.'
                    if val is not None and (find_count.value is None or val > find_count.value):
                        create_flag(instance=count, reason=msg, caused_by=user, reason_type=Flag.FlagReason.MPRE)
                    else:
                        resolve_flag(count.flags, msg)

    
    def __get_related_counts(self, group):
        logic_group = LogicGroup.objects.filter(indicator=group.indicator).first()
        if not logic_group:
            return None

        prereq_inds = LogicCondition.objects.filter(
            group=logic_group,
            source_type=LogicCondition.SourceType.ASS
        ).values_list('source_indicator__id', flat=True)

        if not prereq_inds:
            return None

        # Prefetch indicator types for breakdown logic
        indicator_types = dict(
            Indicator.objects.filter(id__in=prereq_inds)
            .values_list('id', 'type')
        )
        #find a count that overlaps with this one, has the prerequisite indicator, and belongs to the same org
        filters = {
            'group__start__lt': group.end,
            'group__end__gt': group.start,
            'group__organization': group.organization,
            'group__project': group.project,
            'group__indicator__in': prereq_inds
        }
        counts = AggregateCount.objects.filter(**filters)
        counts_map = {}

        for c in counts:
            indicator_type = indicator_types.get(c.group.indicator_id)
            key = self.__make_breakdown_key(c.group.indicator_id, c, indicator_type)
            counts_map[key] = c

        return counts_map
    
    def __check_downstream(self, group, saved_instances, user):
        potential_downstream_ids = LogicCondition.objects.filter(source_indicator=group.indicator).values_list('group__indicator__id', flat=True)
        filters = {
            'group__start__lt': group.end,
            'group__end__gt': group.start,
            'group__organization': group.organization,
            'group__project': group.project,
            'group__indicator__in': potential_downstream_ids
        }   
        downstream_counts = AggregateCount.objects.filter(**filters)
        if downstream_counts.exists():
            downstream_conditions = {
                ind_id: list(LogicCondition.objects.filter(group__indicator_id=ind_id).select_related('source_indicator'))
                for ind_id in potential_downstream_ids
            }
            counts_map = {
                self.__make_breakdown_key(c.group.indicator_id, c, c.group.indicator.type): c
                for c in saved_instances
            }
            for count in downstream_counts:
                conditions = downstream_conditions.get(count.group.indicator_id, [])
                self.__check_logic(
                    indicator=count.group.indicator, 
                    count=count, 
                    user=user, 
                    related=counts_map, 
                    conditions=conditions
                )
    
    def __check_counts(self, group, saved_instances, user):
        related_counts = self.__get_related_counts(group)
        if related_counts is None: #no logic, just check to see if anything downstream should be fixed/created
            self.__check_downstream(group, saved_instances, user)
            return
        if not related_counts: #empty dict means no matching count, flag all counts, check downstream 
            for count in saved_instances:
                create_flag(count, f'Count for Indicator "{group.indicator.name}" is missing prerequsite counts.', user, Flag.FlagReason.MPRE)
            self.__check_downstream(group, saved_instances, user)
            return
        #check if individual counts are mismatched
        conditions = LogicCondition.objects.filter(group__indicator=group.indicator).select_related('source_indicator')
        for count in saved_instances:
            self.__check_logic(
                indicator=group.indicator, 
                count=count,
                user=user, 
                related=related_counts, 
                conditions=conditions, 
            )
        self.__check_downstream(group, saved_instances, user)
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
            self.__check_counts(group, saved_instances, user)            
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
            self.__check_counts(instance, saved_instances, user)  
        return instance