from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db.models import Max

from indicators.models import Indicator, Assessment, Option, LogicCondition, LogicGroup
from profiles.serializers import ProfileListSerializer

class LogicConditionSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    
    class Meta:
        model=LogicCondition
        fields = [
            'id', 'operator', 'source_type', 'source_indicator', 'respondent_field', 'value_text', 'condition_type',
            'value_option', 'value_boolean', 'created_at', 'created_by', 'updated_by', 'updated_at'
        ]

class LogicGroupSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    conditions = serializers.SerializerMethodField()
    def get_conditions(self, obj):
        inds = LogicCondition.objects.filter(group=obj)
        return LogicConditionSerializer(inds, many=True).data
    class Meta:
        model=LogicGroup
        fields = [
            'id', 'group_operator', 'conditions',  'created_by', 'created_at', 'updated_by', 'updated_at',
        ]
    
class OptionSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    class Meta:
        model=Option
        fields = [
            'id', 'name', 'created_by', 'created_at', 'updated_by', 'updated_at', 'deprecated'
        ]

class AssessmentListSerializer(serializers.ModelSerializer):
    '''
    Simple index serializer. We also attach a subcateogry count that's helpful for frontend checks 
    that handle then match subcategory category.
    '''
    display_name = serializers.SerializerMethodField(read_only=True)
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    
    class Meta:
        model=Assessment
        fields = ['id', 'display_name', 'name', 'description', 'created_by', 'created_at', 'updated_by', 'updated_at']

class IndicatorSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    logic = serializers.SerializerMethodField()
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    match_options_id = serializers.PrimaryKeyRelatedField(
        source='match_options',
        queryset=Indicator.objects.all(),
        write_only=True,
        required=False, 
        allow_null=True
    )
    assessment_id = serializers.PrimaryKeyRelatedField(
        source='assessment',
        queryset=Assessment.objects.all(),
        write_only=True,
        required=False, 
        allow_null=True
    )
    assessment = AssessmentListSerializer(read_only=True)
    options_data = serializers.JSONField(write_only=True, required=False)
    logic_data = serializers.JSONField(write_only=True, required=False)
    display_name = serializers.SerializerMethodField(read_only=True)
    
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    def get_options(self, obj):
        opts = []
        if obj.match_options:
            opts = Option.objects.filter(indicator=obj.match_options, deprecated=False)
        else:
            opts = Option.objects.filter(indicator=obj, deprecated=False)
        return OptionSerializer(opts, many=True).data

    def get_logic(self, obj):
        log = LogicGroup.objects.filter(indicator=obj).first()
        return LogicGroupSerializer(log).data
    
    class Meta:
        model=Indicator
        fields = [
            'id', 'display_name', 'name', 'type', 'options', 'order',  'created_by', 'created_at', 'updated_by', 'updated_at',
            'assessment_id', 'options_data', 'logic', 'logic_data', 'match_options', 'match_options_id', 'category', 'allow_none',
            'required', 'allow_aggregate', 'assessment', 'description',
        ]

    def validate(self, attrs):
        user = self.context['request'].user
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to create an indicator')
        if attrs.get('category') == Indicator.Category.ASS and not attrs.get('assessment'):
            raise serializers.ValidationError("Assessment is required for this category")

        ind_type = attrs.get('type')
        options_data = attrs.get('options_data') or []
        match_options = attrs.get('match_options', None)
        
        name = attrs.get('name', None)
        if not name:
            raise serializers.ValidationError('Name is required.')
        if Indicator.objects.filter(name=name).exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError('Name is already in use. Please check if this indicator is already in the system.')

        if match_options:
            if ind_type != Indicator.Type.MULTI:
                return serializers.ValidationError("Only Multiselect indicators can support match options.")
            if match_options.type != Indicator.Type.MULTI:
                return serializers.ValidationError("Only Multiselect indicators can be used as a reference for match_options.")
       
        if ind_type in [Indicator.Type.SINGLE, Indicator.Type.MULTI]:
            if not options_data and not attrs.get('match_options'):
                raise serializers.ValidationError("This indicator type requires options.")
            seen = []
            for option in options_data:
                name = option.get('name')
                if name in seen:
                    raise serializers.ValidationError('You cannot have the same name for two options.')
                seen.append(name)
        

        logic_data = attrs.get('logic_data', {})
        # if logic data
        if logic_data and attrs.get('category') != Indicator.Category.ASS:
            raise serializers.ValidationError('Logic cannot be applied to this indicator.')
        
        if logic_data:
            #if conditions are not provided or the list is empty, throw an error
            if not logic_data.get('conditions', []):
                raise serializers.ValidationError('At least one condition is required to create logic.')
            #check each condition
            for condition in logic_data.get('conditions', []):
                #check if this is comparing to an indicator a respondent field
                st = condition.get('source_type')
                # if a indicator field (either this assessment or including previous ones)
                
                if st in [LogicCondition.SourceType.ASS]:
                    prereq_id = condition.get('source_indicator') #grab the indicator id
                    prereq = Indicator.objects.filter(id=prereq_id).first() #make sure this indicator exists
                    
                    if not prereq:
                        raise serializers.ValidationError('A valid indicator is required.')
                    operator = condition.get('operator')
                    if operator not in LogicCondition.Operator.values:
                        raise serializers.ValidationError(f'Invalid operator "{operator}".')
                    if prereq.type in [Indicator.Type.MULTI, Indicator.Type.BOOL, Indicator.Type.SINGLE]:
                        if operator not in [LogicCondition.Operator.EQUALS, LogicCondition.Operator.NE]:
                            raise serializers.ValidationError('Indicators of this type can only accept "equal to" or "not equal to" as the operator.')
                    if operator in [LogicCondition.Operator.GT, LogicCondition.Operator.LT]:
                        print(prereq.type)
                        if prereq.type not in [Indicator.Type.INT]:
                            raise serializers.ValidationError('This operator can only be applied to indicators that accept a number.')
                        value = condition.get('value_text')
                        try:
                            value = int(value)
                        except (TypeError, ValueError):
                            raise serializers.ValidationError(f'Greater Than/Less Than requires a number')
                    condition_type = condition.get('condition_type')
                    if condition_type and prereq.type not in [Indicator.Type.MULTI, Indicator.Type.SINGLE]:
                        raise serializers.ValidationError('Condition types only apply to indicators with manually created options.')
        
                    if condition_type == LogicCondition.ExtraChoices.ALL and prereq.type != Indicator.Type.MULTI:
                        raise serializers.ValidationError('Cannot apply "all" to a single select question.')
                    if condition_type == LogicCondition.ExtraChoices.NONE and not prereq.allow_none:
                        raise serializers.ValidationError('Cannot apply "none" to an indicator that does not allow for a none option.')
                    if operator in [LogicCondition.Operator.DNC, LogicCondition.Operator.C] and prereq.type not in [Indicator.Type.TEXT]:
                        raise serializers.ValidationError('This operator can only be applied to indicators that accept open text responses.')

                    option = condition.get('value_option', None)
                    if prereq.type in [Indicator.Type.MULTI, Indicator.Type.SINGLE]: #if it is linked to options... # pull the value_option field (an int id)
                        if condition_type and option:
                            raise serializers.ValidationError('Provide either a condition type or an option.')
                        valid_extra_choices = [c[0] for c in LogicCondition.ExtraChoices.choices]
                        if option is None and condition_type not in valid_extra_choices:
                            raise serializers.ValidationError('An option or condition type is required for this condition.') #raise error if blank
                        if not condition_type:
                            try:
                                option = int(option)
                            except (TypeError, ValueError):
                                raise serializers.ValidationError(f'Invalid option ID: {option}')
                            if not prereq.match_options and not option in Option.objects.filter(indicator_id=prereq_id).values_list('id', flat=True): # raise error if not a valid option
                                raise serializers.ValidationError(f'"{option}" is not a valid option for this indicator')
                            elif prereq.match_options:
                                prereq_indicator = Indicator.objects.filter(id=prereq_id).first()
                                if not prereq_indicator:
                                    raise serializers.ValidationError(f'Prerequisite indicator {prereq_id} does not exist')
                                match_to = prereq_indicator.match_options
                                if not option in Option.objects.filter(indicator=match_to).values_list('id', flat=True):
                                    raise serializers.ValidationError(f'"{option}" is not a valid option for this indicator')
                    
                    if prereq.type not in [Indicator.Type.MULTI, Indicator.Type.SINGLE] and option:
                        raise serializers.ValidationError('Only multi and single select indicators can accept an option property.')

                    bool = condition.get('value_boolean')
                    if prereq.type == Indicator.Type.BOOL and not bool in [True, False]:
                        raise serializers.ValidationError('Please provide a true/false to check when creating a condition.')
                    
                    if prereq.type not in [Indicator.Type.BOOL] and bool:
                        raise serializers.ValidationError('Only yes/no indicators can accept an boolean property.')
                    
                    if prereq.type in [Indicator.Type.TEXT, Indicator.Type.INT] and condition.get('value_text') in [None, '']: #otherwise there should be a free response, make sure some value is provided
                        raise serializers.ValidationError('Please provide a value to check when creating a condition.')
                    
                    if prereq.type in [Indicator.Type.INT]:
                        try:
                            valid = int(condition.get('value_text'))
                        except (TypeError, ValueError):
                            raise serializers.ValidationError(f'Logic relying on a numeric indicator must have a valid number.')
                        
                #else if this is checking against a respondent field
                elif st == LogicCondition.SourceType.RES:
                    field = condition.get('respondent_field')
                    if not field or field not in LogicCondition.RespondentField.values: #make sure its a valid field
                        raise serializers.ValidationError('Not a valid respondent field')
                    if field in LogicCondition.RESPONDENT_VALUE_CHOICES.keys(): #make sure the value_text prop contains a valid value for that field
                        if not condition.get('value_text') in [o.get('value') for o in LogicCondition.RESPONDENT_VALUE_CHOICES[field]]:
                            raise serializers.ValidationError(f'"{condition.get("value_text")}" is not a valid choice for respondent field {field}.')
        
        if attrs.get('category') in [Indicator.Category.SOCIAL, Indicator.Category.EVENTS, Indicator.Category.ORGS]: #these should be linked to another object via a task
            if attrs.get('allow_aggregate', False):
                raise serializers.ValidationError('Aggregates are not allowed for this indicator category.')
        if ind_type in [Indicator.Type.TEXT]:
            if attrs.get('allow_aggregate', False):
                raise serializers.ValidationError('Aggregates are not allowed for this indicator type.')    

        
        return attrs
    
    def __set_options(self, user, indicator, options_data):
        if len(options_data) == 0:
            return
        if indicator.type not in [Indicator.Type.SINGLE, Indicator.Type.MULTI, Indicator.Type.MULTINT]:
            raise serializers.ValidationError(f'{indicator} cannot accept options.')
        for option in options_data:
            existing=None
            id = option.get('id')
            if id:
                existing = Option.objects.filter(id=id).first()
            if existing:
                existing.name = option.get('name')
                existing.deprecated = False
                existing.save()
            else:
                new = Option.objects.create(
                    indicator=indicator,
                    name=option.get('name'),
                    deprecated=False,
                )
                option['id'] = new.id
        existing_options = set(Option.objects.filter(indicator=indicator).values_list('id', flat=True))
        submitted_options = set([opt['id'] for opt in options_data if 'id' in opt])
        to_deprecate = existing_options - submitted_options
        Option.objects.filter(id__in=to_deprecate).update(deprecated=True)

    def __set_logic(self, user, indicator, logic_data):
        if len(logic_data) == 0:
            return
        if indicator.category != Indicator.Category.ASS:
            raise serializers.ValidationError('Indicator of this category cannot accept logic rules')
        group=None
        existing = LogicGroup.objects.filter(indicator=indicator).first()
        if existing:
            existing.group_operator =  logic_data.get('group_operator')
            existing.updated_by = user
            existing.save()
            group=existing
            LogicCondition.objects.filter(group=existing).delete() #clear existing conditions before adding new ones
        else:
            group = LogicGroup.objects.create(
                indicator=indicator, 
                group_operator=logic_data.get('group_operator'),
                created_by=user,
            )
        
        for condition in logic_data.get('conditions', []):
            st = condition.get('source_type')
            op = condition.get('operator')
            value_text = condition.get('value_text', None)
            value_boolean = condition.get('value_boolean', None)
            value_option = Option.objects.filter(id=condition.get('value_option')).first() if condition.get('value_option') else None
            condition_type = condition.get('condition_type', None)
            if condition_type:
                value_option = None
            prereq = None
            ind_id = condition.get('source_indicator', None)
            if ind_id:
                prereq = Indicator.objects.filter(id=ind_id).first()
                if not prereq:
                    raise serializers.ValidationError('A valid indicator id is required for source indicator.')
                if prereq.type == Indicator.Type.MULTINT:
                    raise serializers.ValidationError('Indicators of the multiple numbers type cannot be used as source indicators.')
            respondent_field = condition.get('respondent_field', None)

            LogicCondition.objects.create(
                group=group,
                source_type = st,
                operator=op,
                value_text=value_text,
                value_option=value_option,
                condition_type=condition_type,
                value_boolean=value_boolean,
                source_indicator= prereq,
                respondent_field=respondent_field,
                created_by = user
            )

        
    def create(self, validated_data):
        user = self.context['request'].user
        
        options_data = validated_data.pop('options_data', [])
        logic_data = validated_data.pop('logic_data', {}) or {}
        indicator = Indicator.objects.create(**validated_data)
        pos = Indicator.objects.filter(assessment=indicator.assessment).count()
        indicator.order = pos - 1 if pos > 0 else 0
        self.__set_options(user, indicator, options_data)
        self.__set_logic(user, indicator, logic_data)
        indicator.created_by = user
        indicator.save()
        return indicator

    def update(self, instance, validated_data):
        user = self.context['request'].user
        
        options_data = validated_data.pop('options_data', [])
        logic_data = validated_data.pop('logic_data', {}) or {}
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        self.__set_options(user, instance, options_data)
        self.__set_logic(user, instance, logic_data)
        instance.updated_by = user
        instance.save()
        return instance



class AssessmentSerializer(serializers.ModelSerializer):
    '''
    Simple index serializer. We also attach a subcateogry count that's helpful for frontend checks 
    that handle then match subcategory category.
    '''
    display_name = serializers.SerializerMethodField(read_only=True)
    indicators = serializers.SerializerMethodField(read_only=True)
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)

    def get_indicators(self, obj):
        inds = Indicator.objects.filter(assessment=obj)
        return IndicatorSerializer(inds, many=True).data
        
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    
    class Meta:
        model=Assessment
        fields = [
                'id', 'display_name', 'name', 'description', 'created_by', 'created_at', 'updated_by', 
                'updated_at', 'indicators'
        ]
    
    def create(self, validated_data):
        user = self.context['request'].user
        user = self.context['request'].user
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to create an indicator')
        ass = Assessment.objects.create(**validated_data)
        ass.created_by = user
        ass.save()
        return ass

    def update(self, instance, validated_data):
        user = self.context['request'].user
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to create an indicator')
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.updated_by = user
        instance.save()
        return instance