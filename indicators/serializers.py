from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from indicators.models import Indicator, IndicatorSubcategory
from profiles.serializers import ProfileListSerializer

class IndicatorSubcategorySerializer(serializers.ModelSerializer):
    '''
    Simple nested serializer for collecting subcategory information as necessary
    '''
    id = serializers.IntegerField(required=False, allow_null=True)
    class Meta:
        model = IndicatorSubcategory
        fields = ['id', 'name', 'deprecated']

class IndicatorListSerializer(serializers.ModelSerializer):
    '''
    Simple index serializer. We also attach a subcateogry count that's helpful for frontend checks 
    that handle then match subcategory category.
    '''
    subcategories = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField(read_only=True)

    def get_subcategories(self, obj):
        return obj.subcategories.filter(deprecated=False).count()
    
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    
    class Meta:
        model=Indicator
        fields = ['id', 'display_name', 'subcategories', 'indicator_type']

class IndicatorSerializer(serializers.ModelSerializer):
    '''
    Main serializer that handles the indicator model proper.
    '''
    subcategories = serializers.SerializerMethodField()
    subcategory_data = IndicatorSubcategorySerializer(many=True, write_only=True, required=False)
    required_attribute_names = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )

    prerequisites = IndicatorListSerializer(read_only=True, many=True)
    prerequisite_ids = serializers.PrimaryKeyRelatedField(
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
    display_name = serializers.SerializerMethodField(read_only=True)
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)

    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    
    def get_subcategories(self, obj):
        '''
        Collect non-deprecated subcategories
        '''
        active_subcats = obj.subcategories.filter(deprecated=False)
        return IndicatorSubcategorySerializer(active_subcats, many=True).data
        
    class Meta:
        model = Indicator
        fields = ['id', 'name', 'code', 'prerequisites', 'prerequisite_ids', 'description', 'subcategories', 'match_subcategories_to',
                  'subcategory_data', 'require_numeric', 'status', 'created_by', 'created_at', 'allow_repeat', 'governs_attribute',
                  'updated_by', 'updated_at', 'required_attributes', 'required_attribute_names', 'indicator_type', 'display_name']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)

        # Lazy import to avoid circular dependency
        from respondents.serializers import RespondentAttributeTypeSerializer

        representation['required_attributes'] = RespondentAttributeTypeSerializer(
            instance.required_attributes.all(), many=True
        ).data

        return representation
    
    def validate_prerequisite_ids(self, value):
        '''
        Special validation for prerequisites
        '''
        if not value:
            return None
        if self.instance:
            for prereq in value:
                if prereq == self.instance:
                    raise serializers.ValidationError("An indicator cannot be its own prerequisite.")
                if prereq.indicator_type != self.instance.indicator_type:
                    raise serializers.ValidationError("Prerequisites must match the indicator type.")
        return value

    def validate(self, attrs):
        user = self.context['request'].user
        
        #only admins can create indicators
        if user.role != 'admin':
            raise PermissionDenied('You do not have permission to create an indicator')
        
        code = attrs.get('code', getattr(self.instance, 'code', None))
        name = attrs.get('name', getattr(self.instance, 'name', None))
        status = attrs.get('status', getattr(self.instance, 'status', None))
        indicator_type = attrs.get('indicator_type', getattr(self.instance, 'indicator_type', None))
        prerequisites = attrs.get('prerequisites', getattr(self.instance, 'prerequisites', []))
        required_attributes = attrs.get('required_attribute_names', getattr(self.instance, 'required_attributes', None))
        governs_attribute = attrs.get('governs_attribute', getattr(self.instance, 'governs_attribute', None))
        ind_id = self.instance.id if self.instance else None
        match_subcategories_to = attrs.get('match_subcategories_to', None)
        subcategory_data = attrs.get('subcategory_data', [])

        ###===CODE AND NAME ARE REQUIRES AND MUST BE UNIQUE===###
        if not code:
            raise serializers.ValidationError({"code": "Code is required."})
        if not name:
            raise serializers.ValidationError({"name": "Name is required."})
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
        ###===Check prerequisite statuses===###
        if prerequisites:
            if hasattr(prerequisites, 'all'):
                prerequisites = list(prerequisites.all())
            for prerequisite in prerequisites:
                if prerequisite.status == 'deprecated':
                    raise serializers.ValidationError({"prerequisites": "This selected prerequisite indicator has been marked as deprecated, and therefore cannot be used as a prerequiste."})
                if status == 'active' and prerequisite.status == 'planned':
                    raise serializers.ValidationError({"prerequisites": "This indicator's prerequisite is not active although this indicator was marked as active. Please set that indicator as active first."})
                if indicator_type != prerequisite.indicator_type:
                    raise serializers.ValidationError({"prerequisites": f"This indicator is marked as type {indicator_type} which does not match the selected prerequisite {prerequisite.indicator_type} ."})
        
        ###===Make sure an edit won't invalidate a downstream indicator===###
        if ind_id:
            dependencies = Indicator.objects.filter(prerequisites__id = ind_id)
            if dependencies:
                for dep in dependencies:
                    if indicator_type != dep.indicator_type:
                        raise serializers.ValidationError({"indicator type": f"Indicator {dep.name} uses this indicator as a prerequisite. You may not change this indicators type, as it will invalidate that indicator."})
                    if dep.status != 'deprecated' and status =='deprecated':
                        raise serializers.ValidationError({"status": f"Indicator {dep.name} uses this indicator as a prerequisite. You must deprecate that indicator first."})
                    elif dep.status == 'active' and status == 'planned':
                        raise serializers.ValidationError({"status": f"Indicator {dep.name} is active and uses this indicator as a prerequisite. You must mark that indicator as planned first."})
        ###===Make sure that for this indicator to rely on an attribute, it is of the correct type===###
        if required_attributes and indicator_type != 'respondent':
            raise serializers.ValidationError({"required_attributes": "For this indicator to have required attributes, its type must be set to 'Respondent'."})
        if governs_attribute and indicator_type != 'respondent':
            raise serializers.ValidationError({"governs_attribute": "For this indicator to be able to govern attributes, its type must be set to 'Respondent'."})
        if match_subcategories_to and not prerequisites:
            raise serializers.ValidationError({"match_subcategories_to": "Matching subcategories is only allowed for indicators with a prerequisite."})
        if match_subcategories_to and not match_subcategories_to in prerequisites:
            raise serializers.ValidationError({"match_subcategories_to": "Cannot match subcategories with an indicator that has no subcategories."})
        
        ###===Sanity check to make sure there isn't ever conflict subcateogry data===###
        if len(subcategory_data) > 0 and match_subcategories_to:
            prereq_ids = [c.id for c in match_subcategories_to.subcategories.all()]
            child_ids = [c.get('id') for c in subcategory_data]
            if set(prereq_ids) != set(child_ids):
                raise serializers.ValidationError({"match_subcategories_to": "Found conflicting requests to match subcategories and provide unique subcategory values."})
        return attrs
    
    def validate_governs_attribute(self, value):
        '''
        Make sure that all attributes are valid choices.
        '''
        if not value:
            return None
        from respondents.models import RespondentAttributeType
        valid_choices = set(choice[0] for choice in RespondentAttributeType.Attributes.choices)
        if value not in valid_choices:
            raise serializers.ValidationError(f"{value} is not a valid attribute.")
        return value

    def validate_required_attribute_names(self, value):
        '''
        Make sure that all attributes are valid choices.
        '''
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
        if prerequisites is not None:
            indicator.prerequisites.set(prerequisites)

        #if matched subcats, set them equal here
        if indicator.match_subcategories_to:
            prereq_subcats = IndicatorSubcategory.objects.filter(indicator=indicator.match_subcategories_to)
            indicator.subcategories.set(prereq_subcats)
        #else, verify the names and create new categories
        else:
            cleaned_names = [
                name.get('name').replace(',', '').replace(':', '') for name in subcategory_data if name.get('name')
            ]   #these chars are used for file uploads, and so are not allowed as names
            subcategories = [
                IndicatorSubcategory.objects.create(name=name, deprecated=False)
                for name in cleaned_names
            ]
            indicator.subcategories.set(subcategories)
        
        #create required attributes as well
        attrs = [
            RespondentAttributeType.objects.get_or_create(name=name)[0]
            for name in required_attribute_names
        ]
        indicator.required_attributes.set(attrs)

        return indicator

    def update(self, instance, validated_data):
        from respondents.models import RespondentAttributeType
        prerequisites = validated_data.pop('prerequisites', [])

        #for our m2m fields, nothing attached for a partial does nothing, an empty array wipes
        subcategory_data = validated_data.pop('subcategory_data', None) 
        required_attribute_names = validated_data.pop('required_attribute_names', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        print(prerequisites)
        if 'prerequisite_ids' in self.initial_data:
            if prerequisites is None:
                prerequisites = []
            instance.prerequisites.set(prerequisites)

        #same as above, match or set the subcategories
        if instance.match_subcategories_to:
            prereq_subcats = IndicatorSubcategory.objects.filter(indicator=instance.match_subcategories_to)
            instance.subcategories.set(prereq_subcats)
        elif not subcategory_data and 'match_subcategories_to' in self.initial_data and validated_data.get('match_subcategories_to') is None:
            instance.subcategories.set([])
        else:
            subcategories = []
            if subcategory_data is not None:
                for cat in subcategory_data:
                    #check if a request was made to deprectate the indicator
                    deprecated = str(cat.get('deprecated')).strip().lower() in ['true', '1']
                    name = cat.get('name')
                    if not name:
                        raise serializers.ValidationError(f'Subcategory name may not be blank.')
                    name = name.replace(',', '').replace(':', '')
                    existing_id = cat.get('id')

                    #check if its an existing name change or new, then create/update
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

                #also update any indciators that may need to match this ones subcategories
                children = Indicator.objects.filter(prerequisites=instance, match_subcategories_to=self.instance)
                for child in children:
                    child.subcategories.set(subcategories)
        
        #create the required attributes
        if required_attribute_names is not None:
            attrs = [
                RespondentAttributeType.objects.get_or_create(name=name)[0]
                for name in required_attribute_names
            ]
            instance.required_attributes.set(attrs)
        return instance