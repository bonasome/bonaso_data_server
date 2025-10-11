from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from indicators.models import Indicator, Assessment, Option, LogicCondition, LogicGroup
from profiles.serializers import ProfileListSerializer

class LogicConditionSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    class Meta:
        model=LogicCondition
        fields = [
            'id', 'operator', 'source_type', 'source_indicator', 'respondent_field', 'value_text', 
            'value_option', 'created_at', 'updated_by', 'updated_at', 'deprecated'
        ]

class LogicGroupSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    conditions = serializers.SerializerMethodField()
    def get_conditions(self, obj):
        inds = LogicCondition.objects.filter(group=obj)
        return LogicConditionSerializer(inds, many=True)
    
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
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    assessment_id = serializers.PrimaryKeyRelatedField(
        source='assessment',
        queryset=Assessment.objects.all(),
        write_only=True,
        required=False, 
        allow_null=True
    )
    options_data = serializers.JSONField(write_only=True, required=False)
    logic_data = serializers.JSONField(write_only=True, required=False)
    
    class Meta:
        model=Indicator
        fields = [
            'id', 'name', 'type', 'options', 'index',  'created_by', 'created_at', 'updated_by', 'updated_at',
            'assessment_id', 'options_data', 'logic_data'
        ]

    def validate(self, attrs):
        user = self.context['request'].user
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to create an indicator')
        if attrs.get('category') == Indicator.Category.ASS and not attrs.get('assessment_id'):
            raise serializers.ValidationError("Assessment is required for this category")
        if attrs.get('category') == Indicator.Category.ASS:
            assessment = get_object_or_404(Assessment, id=attrs.get('assessment_id'))

        ind_type = attrs.get('type')
        options_data = attrs.get('options_data') or []
        if ind_type in [Indicator.Type.SINGLE, Indicator.Type.MULTI]:
            if not options_data:
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
                    prereq_id = condition.get('indicator') #grab the indicator id
                    prereq = get_object_or_404(Indicator, id=prereq_id) #make sure this indicator exists
                    if prereq.type in [Indicator.Type.MULTI, Indicator.Type.SINGLE]: #if it is linked to options...
                        option = condition.get('value_option', None) # pull the value_option field (an int id)
                        if not option:
                            raise serializers.ValidationError('An option is required for this condition.') #raise error if blank
                        if not option in Option.objects.filter(indicator_id=prereq_id).values_list('id', flat=True): # raise error if not a valid option
                            raise serializers.ValidationError(f'"{option}" is not a valid option for this indicator')
                    elif not condition.get('value_text'): #otherwise there should be a free response, make sure some value is provided
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
        if indicator.category != Indicator.Category.ASS:
            raise serializers.ValidationError('Indicator of this category cannot accept logic rules')
        group=None
        existing = LogicGroup.objects.filter(indicator=indicator).first()
        if existing:
            existing.operator =  logic_data.get('operator')
            existing.updated_by = user
            existing.save()
            group=existing
            LogicCondition.objects.filter(group=existing).delete() #clear existing conditions before adding new ones
        else:
            group = LogicGroup.objects.create(
                indicator=indicator, 
                operator=logic_data.get('operator'),
                created_by=user,
            )
        
        for condition in logic_data.get('conditions', []):
            st = condition.get('source_type')
            op = condition.get('operator')
            value_text = condition.get('value_text', None)
            value_option = Option.objects.filter(id=condition.get('value_option_id')).first() if condition.get('value_option_id') else None
            prereq = condition.get('indicator', None)
            respondent_field = condition.get('respondent_field', None)
            LogicCondition.objects.create(
                group=group,
                source_type = st,
                operator=op,
                value_text=value_text,
                value_option=value_option,
                source_indicator= prereq,
                respondent_field=respondent_field,
                created_by = user
            )

    def create(self, validated_data):
        user = self.context['request'].user
        
        options_data = validated_data.pop('options_data', [])
        logic_data = validated_data.pop('logic_data', {}) or {}
        indicator = Indicator.objects.create(**validated_data)
        self.__set_options(user, indicator, options_data)
        self.__set_logic(user, indicator, logic_data)
        indicator.created_by = user
        indicator.save()
        return indicator

    def update(self, instance, validated_data):
        user = self.context['request'].user
        
        options_data = validated_data.pop('options_data', [])
        logic_data = validated_data.pop('logic_data', {}) or {}
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
        fields = ['id', 'display_name',  'created_by', 'created_at', 'updated_by', 'updated_at']

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
        return IndicatorSerializer(inds, many=True)
        
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    
    class Meta:
        model=Assessment
        fields = ['id', 'display_name', 'created_by', 'created_at', 'updated_by', 'updated_at', 'indicators']