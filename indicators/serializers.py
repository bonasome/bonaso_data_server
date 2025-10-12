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
            'id', 'operator', 'source_type', 'source_indicator', 'respondent_field', 'value_text', 
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
        model=Assessment
        fields = [
            'id', 'name', 'type', 'options', 'created_by', 'created_at', 'updated_by', 'updated_at', 'deprecated'
        ]

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
    options_data = serializers.JSONField(write_only=True, required=False)
    logic_data = serializers.JSONField(write_only=True, required=False)
    display_name = serializers.SerializerMethodField(read_only=True)
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    def get_options(self, obj):
        opts = Option.objects.filter(indicator=obj)
        return OptionSerializer(opts, many=True).data

    def get_logic(self, obj):
        log = LogicGroup.objects.filter(indicator=obj).first()
        return LogicGroupSerializer(log).data
    
    class Meta:
        model=Indicator
        fields = [
            'id', 'display_name', 'name', 'type', 'options', 'order',  'created_by', 'created_at', 'updated_by', 'updated_at',
            'assessment_id', 'options_data', 'logic', 'logic_data', 'match_options', 'match_options_id'
        ]

    def validate(self, attrs):
        user = self.context['request'].user
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to create an indicator')
        if attrs.get('category') == Indicator.Category.ASS and not attrs.get('assessment_id'):
            raise serializers.ValidationError("Assessment is required for this category")
        if attrs.get('category') == Indicator.Category.ASS:
            assessment = Assessment.objects.filter(id=attrs.get('assessment_id')).first()
            if not assessment:
                raise serializers.ValidationErrors('Must provide a valid assessment.')

        ind_type = attrs.get('type')
        options_data = attrs.get('options_data') or []
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
        if logic_data:
            #if conditions are not provided or the list is empty, throw an error
            if not logic_data.get('conditions', []):
                raise serializers.ValidationError('At least one condition is required to create logic.')
            #check each condition
            for condition in logic_data.get('conditions', []):
                #check if this is comparing to an indicator a respondent field
                st = condition.get('source_type')
                # if a indicator field (either this assessment or including previous ones)
                
                if st in [LogicCondition.SourceType.ASS, LogicCondition.SourceType.IND]:
                    prereq_id = condition.get('source_indicator') #grab the indicator id
                    prereq = Indicator.objects.filter(id=prereq_id).first() #make sure this indicator exists
                    
                    if not prereq:
                        raise serializers.ValidationError('A valid indicator is required.')
                    
                    if prereq.type in [Indicator.Type.MULTI, Indicator.Type.SINGLE]: #if it is linked to options...
                        option = condition.get('value_option', None) # pull the value_option field (an int id)
                        if option is None:
                            raise serializers.ValidationError('An option is required for this condition.') #raise error if blank
                        if not option in Option.objects.filter(indicator_id=prereq_id).values_list('id', flat=True): # raise error if not a valid option
                            raise serializers.ValidationError(f'"{option}" is not a valid option for this indicator')
                    
                    elif prereq.type == Indicator.Type.BOOL and not condition.get('value_boolean') in [True, False]:
                        raise serializers.ValidationError('Please provide a true/false to check when creating a condition.')
        
                    elif prereq.type in [Indicator.Type.TEXT, Indicator.Type.INT] and condition.get('value_text') in [None, '']: #otherwise there should be a free response, make sure some value is provided
                        raise serializers.ValidationError('Please provide a value to check when creating a condition.')
                
                #else if this is checking against a respondent field
                
                elif st == LogicCondition.SourceType.RES:
                    field = condition.get('respondent_field')
                    if not field or field not in LogicCondition.RespondentField.choices: #make sure its a valid field
                        raise serializers.ValidationError('Not a valid respondent field')
                    if field in LogicCondition.RESPONDENT_VALUE_CHOICES.keys: #make sure the value_text prop contains a valid value for that field
                        if not condition.get('value_text') in LogicCondition.RESPONDENT_VALUE_CHOICES[field]:
                            raise serializers.ValidationError(f'"{condition.get("value_text")}" is not a valid choice for respondent field {field}.')
        return attrs
    
    def __set_options(self, user, indicator, options_data):
        if len(options_data) == 0:
            return
        if indicator.type not in [Indicator.Type.SINGLE, Indicator.Type.MULTI]:
            raise serializers.ValidationError(f'{indicator} cannot accept options.')
        for option in options_data:
            existing=None
            id = option.get('id')
            if id:
                existing = Option.objects.filter(id=id).first()
            if existing:
                existing.name = option.get('name')
                existing.deprecated = option.get('deprecated')
            else:
                Option.objects.create(
                    indicator=indicator,
                    name=option.get('name'),
                    deprecated=option.get('deprecated', False),
                )
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
            value_option = Option.objects.filter(id=condition.get('value_option_id')).first() if condition.get('value_option_id') else None
            prereq = None
            ind_id = condition.get('source_indicator', None)
            if ind_id:
                prereq = Indicator.objects.filter(id=ind_id).first()
            respondent_field = condition.get('respondent_field', None)

            LogicCondition.objects.create(
                group=group,
                source_type = st,
                operator=op,
                value_text=value_text,
                value_option=value_option,
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
        fields = ['id', 'display_name', 'description', 'created_by', 'created_at', 'updated_by', 'updated_at']

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
        ass = Assessment.objects.create(**validated_data)
        ass.created_by = user
        ass.save()
        return ass

    def update(self, instance, validated_data):
        user = self.context['request'].user
        instance.updated_by = user
        instance.save()
        return instance