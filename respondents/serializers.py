from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from datetime import date
from django.utils.timezone import now

from django.db.models import Q

from respondents.models import Respondent, Interaction, Response, Pregnancy, HIVStatus, KeyPopulation, DisabilityType, RespondentAttribute, RespondentAttributeType, KeyPopulationStatus, DisabilityStatus
from respondents.utils import update_m2m_status, respondent_flag_check,  dummy_dob_calc, calculate_age_range, check_logic
from respondents.exceptions import DuplicateExists

from projects.models import Task, ProjectOrganization
from projects.serializers import TaskSerializer

from indicators.models import  Indicator, Option, LogicCondition, LogicGroup
from indicators.serializers import OptionSerializer, IndicatorSerializer
from flags.serializers import FlagSerializer
from profiles.serializers import ProfileListSerializer
from django.contrib.auth import get_user_model
User = get_user_model()

class RespondentListSerializer(serializers.ModelSerializer):
    '''
    Shorthand serializer that only gives essential information for indexes and the like
    '''
    display_name = serializers.SerializerMethodField()
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    class Meta:
        model = Respondent
        fields = [
            'id', 'uuid', 'is_anonymous','sex', 'village', 'district', 'citizenship', 
            'comments', 'age_range', 'display_name'
        ]

'''
Several through table serializers for related models
'''
class RespondentAttributeTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model= RespondentAttributeType
        fields = ['id', 'name']
        
class KPSerializer(serializers.ModelSerializer):
    class Meta:
        model = KeyPopulation
        fields = ['id', 'name']

class DisabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = DisabilityType
        fields = ['id', 'name']

class PregnancySerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    class Meta:
        model = Pregnancy
        fields = ['id', 'term_began', 'term_ended', 'created_by', 'created_at', 'updated_by', 'updated_at']

class HIVStatusSerializer(serializers.ModelSerializer):
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    class Meta:
        model = HIVStatus
        fields = ['id', 'hiv_positive', 'date_positive', 'created_by', 'created_at', 'updated_by', 'updated_at']
    

class RespondentSerializer(serializers.ModelSerializer):
    #id_no = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    display_name = serializers.SerializerMethodField()
    dob = serializers.DateField(required=False, allow_null=True)

    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)

    pregnancies = PregnancySerializer(source='pregnancy_set', many=True, read_only=True)
    pregnancy_data = PregnancySerializer(many=True, write_only=True, required=False)

    hiv_status = HIVStatusSerializer(read_only=True, source='hivstatus')
    hiv_status_data = HIVStatusSerializer(write_only=True, required=False)

    special_attribute = RespondentAttributeTypeSerializer(many=True, read_only=True)
    special_attribute_names = serializers.ListField(
            child=serializers.CharField(), write_only=True, required=False
        )
    kp_status = KPSerializer(read_only=True, many=True)
    kp_status_names = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    
    disability_status = DisabilitySerializer(read_only=True, many=True)
    disability_status_names = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    
    flags = FlagSerializer(read_only=True, many=True)
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()
    class Meta:
        model=Respondent
        fields = [
            'id','id_no', 'uuid', 'is_anonymous', 'first_name', 'last_name', 'sex', 'plot_no', 'ward',
            'village', 'district', 'citizenship', 'comments', 'email', 'phone_number', 'dob',
            'age_range', 'created_by', 'updated_by', 'created_at', 'updated_at', 'special_attribute', 
            'special_attribute_names', 'pregnancies', 'pregnancy_data', 'hiv_status', 'kp_status', 'kp_status_names', 'disability_status',
            'disability_status_names', 'hiv_status_data', 'flags', 'current_age_range', 'display_name'
        ]

    def validate_id_no(self, value):
        #confirm this is not a duplicate (check id_no)
        if not value:
            return value
        if self.instance:
            existing = Respondent.objects.filter(id_no=value).exclude(id=self.instance.id)
        else:
            existing = Respondent.objects.filter(id_no=value)
        if existing.exists():
            raise DuplicateExists(
                detail="This respondent already exists.",
                existing_id=existing.first().id
            )
        return value
    def validate(self, attrs):
        user = self.context['request'].user
        role = getattr(user, 'role', None)
        respondent = self.instance
        if role == 'client':
            raise PermissionDenied("You do not have permission to make edits to interactions.")
        
        #make sure that no sensitive fields are sent with anonymous respondents
        if 'is_anonymous' in attrs:
            if attrs['is_anonymous']:
                for field in ['id_no', 'first_name', 'last_name', 'email', 'phone_number', 'dob']:
                    if attrs.get(field):
                        raise serializers.ValidationError(f"{field} must not be set when is_anonymous is True.")
            else:
                for field in ['id_no', 'first_name', 'last_name', 'dob']:
                    if not attrs.get(field) and not getattr(self.instance, field, None):
                        raise serializers.ValidationError(f"{field} is required when respondent is not anonymous.")
        
        #verify DOB is not in the future
        dob = attrs.get('dob')
        if dob and dob > date.today():
            raise serializers.ValidationError('Date of Birth may not be in the future.')
        
        #verify nothing is off with pregnancy dates
        pregnancies = attrs.get('pregnancy_data')
        if pregnancies:
            for pregnancy in pregnancies:
                term_began = pregnancy.get('term_began', None)
                term_ended = pregnancy.get('term_ended', None)
                #if a pregnancy is set to None (effectively deleted), don't verify
                if not term_began and not term_ended:
                    continue
                #term began is required, term ended is not since a pregnancy can be active
                if not term_began:
                    raise serializers.ValidationError("Pregnancy term start date is required.")
                if term_ended and term_began > term_ended:
                    raise serializers.ValidationError('Pregnancy term start must be after the end')
                if term_began > date.today() or (term_ended and term_ended > date.today()):
                    raise serializers.ValidationError('Pregnancy dates cannot be in the future.')
                base_qs = Pregnancy.objects.filter(respondent=respondent)

                # Check for any potential overlaps (a person can't be pregnant twice and the same time).
                # On update, exclude the existing pregnancy if we're updating it
                pid = pregnancy.get('id')
                if pid:
                    base_qs = base_qs.exclude(id=pid)
                if term_ended:
                    overlaps = base_qs.filter(term_began__lt=term_ended, term_ended__gt=term_began)
                else:
                    overlaps = base_qs.filter(Q(term_ended__isnull=True) | Q(term_ended__gt=term_began))
                if overlaps.exists():
                    raise serializers.ValidationError("This pregnancy overlaps with an existing one.")
                
        #verify date positive is not in the future    
        hiv_status_data = attrs.get('hiv_status_data')
        if hiv_status_data:
            date_positive = hiv_status_data.get('date_positive', None)
            if not date_positive:
                date_positive = date.today()
            if date_positive > date.today():
                    raise serializers.ValidationError('Date Positive cannot be in the future.')
            
        return attrs
    
    def validate_required_attribute_names(self, value):
        #make sure all attribute names provided are valid choices and no rogue values are slipping through
        valid_choices = set(choice[0] for choice in RespondentAttributeType.Attributes.choices)
        auto_choices = {'PLWHIV', 'PWD', 'KP'}
        cleaned = []

        for name in value:
            if name not in valid_choices:
                raise serializers.ValidationError(f"{name} is not a valid attribute.")
            if name in auto_choices:
                raise serializers.ValidationError("Do not manually set PLWHIV, PWD, or KP; these are system-managed.")
            else:
                cleaned.append(name)
        return cleaned
    
    def validate_kp_status_names(self, value):
        #make sure that all the all kp_status names are in line with the set categories from the KP model.
        valid_choices = set(choice[0] for choice in KeyPopulation.KeyPopulations.choices)
        cleaned = []

        for name in value:
            if name not in valid_choices:
                raise serializers.ValidationError(f"{name} is not a valid attribute.")
            cleaned.append(name)
        return cleaned
    
    def validate_disability_status_names(self, value):
        #make sure that the all disability_status names are in line with the set categories from the DType model.
        valid_choices = set(choice[0] for choice in DisabilityType.DisabilityTypes.choices)
        cleaned = []

        for name in value:
            if name not in valid_choices:
                raise serializers.ValidationError(f"{name} is not a valid attribute.")
            cleaned.append(name)
        return cleaned
    
    def create(self, validated_data):
        user = self.context['request'].user

        #pop our M2M/related fields
        special_attribute_names = validated_data.pop('special_attribute_names', [])
        kp_status_names = validated_data.pop('kp_status_names', [])
        disability_status_names = validated_data.pop('disability_status_names', [])
        pregnancies = validated_data.pop('pregnancy_data', [])
        hiv_status_data = validated_data.pop('hiv_status_data', None)
        
        respondent = Respondent.objects.create(**validated_data)
        
        #if the respondent is anonymous, create a dummy date of birth that we can use to at least
        #somewhat accurately track data over time
        if respondent.is_anonymous and respondent.age_range:
            respondent.dummy_dob = dummy_dob_calc(respondent.age_range, respondent.created_at)
        
        if respondent.dob:
            respondent.age_range = calculate_age_range(respondent.dob)

        #run some checks on the Omang --> check respondents.utils.respondent_flag_check for more information on the checks
        if respondent.citizenship == 'BW' and not respondent.is_anonymous and respondent.id_no:
            respondent_flag_check(respondent, user)

        #manually update the m2m fields (see respondents.utils.update_m2m_status)
        attrs = []
        for name in special_attribute_names:
            attr_type, _ = RespondentAttributeType.objects.get_or_create(name=name)
            attr, _ = RespondentAttribute.objects.get_or_create(respondent=respondent, attribute=attr_type)
            attrs.append(attr.attribute)
        respondent.special_attribute.set(attrs)

        
        kp_instances = update_m2m_status(
            model=KeyPopulation,
            through_model=KeyPopulationStatus,
            respondent=respondent,
            name_list=kp_status_names,
            related_field='key_population'
        )
        respondent.kp_status.set(kp_instances)
        
        disability_instances = update_m2m_status(
            model=DisabilityType,
            through_model=DisabilityStatus,
            respondent=respondent,
            name_list=disability_status_names,
            related_field='disability'
        )
        respondent.disability_status.set(disability_instances)

        #set hiv_status
        if hiv_status_data:
            hiv_positive = hiv_status_data.get('hiv_positive', None)
            if hiv_positive:
                hiv_positive = True if hiv_positive in ['true', 'True', True, '1'] else None
                if hiv_positive:
                    date_positive = hiv_status_data.get('date_positive')
                    if not date_positive:
                        date_positive = date.today()
                    HIVStatus.objects.create(
                        respondent=respondent, 
                        hiv_positive=hiv_positive, 
                        date_positive=date_positive,
                        created_by=user
                    )

        #set pregnancies
        for pregnancy in pregnancies:
            term_began = pregnancy.get('term_began', None)
            term_ended = pregnancy.get('term_ended', None)
            if term_began:
                is_pregnant =  term_began and not term_ended
                Pregnancy.objects.create(
                    respondent=respondent, is_pregnant=is_pregnant, term_began=term_began, 
                    term_ended=term_ended, created_by=user)

        respondent.created_by = user
        respondent.save()
        
        return respondent

    def update(self, instance, validated_data):
        user = self.context['request'].user
        #for the m2m fields, if an empty array is sent, we're assuming thats a delete
        #if nothing is sent, ignore it (prevent wiping for partial updates, even though this isn't really expected behavior)
        special_attribute_names = validated_data.pop('special_attribute_names', None)
        kp_status_names = validated_data.pop('kp_status_names', None)
        disability_status_names = validated_data.pop('disability_status_names', None)
        pregnancies = validated_data.pop('pregnancy_data', None)
        hiv_status_data = validated_data.pop('hiv_status_data', None)
        
        instance = super().update(instance, validated_data)
        instance.updated_by = user
        #the model's default save function may override the user provided age_range, so use the validated data version
        if instance.is_anonymous and validated_data.get('age_range'):
            instance.dummy_dob = dummy_dob_calc(validated_data.get('age_range'), instance.created_at)

        if instance.dob and not instance.is_anonymous:
            instance.age_range = calculate_age_range(instance.dob)

        #run flag checks (for creating new flags and resolving old ones) --> more detail at respondents.utils.respondent_flag_check
        if instance.citizenship == 'BW' and not instance.is_anonymous:
            respondent_flag_check(instance, user)
        
        #set m2m fields if provided
        if special_attribute_names is not None:
            attrs = [
                RespondentAttributeType.objects.get_or_create(name=name)[0]
                for name in special_attribute_names
            ]
            auto_attr = [
                RespondentAttributeType.Attributes.PLWHIV,
                RespondentAttributeType.Attributes.KP,
                RespondentAttributeType.Attributes.PWD,
            ]
            auto_gen = instance.special_attribute.filter(name__in=auto_attr)
            attrs += list(auto_gen) 
            instance.special_attribute.set(attrs) 

        if kp_status_names is not None:
            kp_instances = update_m2m_status(
                model=KeyPopulation,
                through_model=KeyPopulationStatus,
                respondent=instance,
                name_list=kp_status_names,
                related_field='key_population'
            )
            instance.kp_status.set(kp_instances)
        if disability_status_names is not None:
            disability_instances = update_m2m_status(
                model=DisabilityType,
                through_model=DisabilityStatus,
                respondent=instance,
                name_list=disability_status_names,
                related_field='disability'
            )
            instance.disability_status.set(disability_instances)

        #set HIV status
        if hiv_status_data is not None:
            hiv_positive = hiv_status_data.get('hiv_positive', None)
            if hiv_positive is not None:
                hiv_positive = True if hiv_positive in ['true', 'True', True, '1'] else False
                if hiv_positive:
                    date_positive = hiv_status_data.get('date_positive') if hiv_positive else None
                if hiv_positive and not date_positive:
                    date_positive = date.today()
                existing = HIVStatus.objects.filter(respondent=instance).first()
                if existing:
                    existing.hiv_positive = hiv_positive
                    existing.date_positive = date_positive if hiv_positive else None
                    existing.updated_by = user
                    existing.updated_at = now()
                    existing.save()
                else:
                        HIVStatus.objects.create(
                            respondent=instance, 
                            hiv_positive=hiv_positive, 
                            date_positive=date_positive if hiv_positive else None,
                            created_by = user
                        )

        #set pregnancy data
        if pregnancies is not None:
            for pregnancy in pregnancies:
                pid = pregnancy.get('id')
                term_began = pregnancy.get('term_began')
                term_ended = pregnancy.get('term_ended')
                is_pregnant =  term_began and not term_ended
                
                if pid:
                    try:
                        pregnancy = Pregnancy.objects.get(id=pid, respondent=instance)
                        if not term_began:
                            pregnancy.delete()
                            continue
                        pregnancy.term_began = term_began
                        pregnancy.term_ended = term_ended
                        pregnancy.is_pregnant =  term_began and not term_ended
                        pregnancy.updated_by = user
                        pregnancy.updated_at = now()
                        pregnancy.save()
                    except Pregnancy.DoesNotExist:
                        raise serializers.ValidationError(f"Invalid pregnancy ID: {pid}")
                else:
                    if term_began:
                        Pregnancy.objects.create(
                            respondent=instance, 
                            is_pregnant=is_pregnant, 
                            term_began=term_began, 
                            term_ended=term_ended,
                            created_by = user
                        )

        #if a respondent is marked as anonymous, clear any existing fields that may be left over from
        # when they may have been a full respondent         
        if instance.is_anonymous:
            instance.first_name = None
            instance.dob = None
            instance.ward = None
            instance.id_no = None
            instance.email = None
            instance.phone_number = None
        instance.save()

        return instance

class ResponseSerializer(serializers.ModelSerializer):
    response_option = OptionSerializer(read_only=True)
    indicator = IndicatorSerializer(read_only=True)
    class Meta:
        model=Response
        fields = [
            'id', 'response_value', 'response_option', 'response_boolean', 'response_date', 'indicator', 
            'response_location',
        ]
        


class InteractionSerializer(serializers.ModelSerializer):
    respondent = RespondentSerializer(read_only=True)
    task = TaskSerializer(read_only=True)
    task_id = serializers.PrimaryKeyRelatedField(
        source='task',
        queryset=Task.objects.all(),
        write_only=True,
    )
    respondent_id = serializers.PrimaryKeyRelatedField(
        source='respondent',
        queryset=Respondent.objects.all(),
        write_only=True,
    )
    
    responses = serializers.SerializerMethodField()
    response_data = serializers.JSONField(write_only=True, required=False)

    def get_responses(self, obj):
        responses = Response.objects.filter(interaction=obj)
        return ResponseSerializer(responses, many=True).data
    
    class Meta:
        model=Interaction
        fields = [
            'id', 'interaction_date', 'interaction_location', 'comments', 'responses', 'response_data',
            'task_id', 'task', 'respondent', 'respondent_id'
        ]

    def __options_valid(self, option, indicator):
        try:
            option = int(option)
        except (TypeError, ValueError):
            return False
        if not indicator.match_options and not option in Option.objects.filter(indicator_id=indicator).values_list('id', flat=True): # raise error if not a valid option
            return False
        elif indicator.match_options:
            if not option in Option.objects.filter(indicator=indicator.match_options).values_list('id', flat=True):
                return False
        return True
    
    def __value_valid(self, indicator, val):
        if indicator.type == Indicator.Type.MULTI:
            if not isinstance(val, list):
                raise serializers.ValidationError('A list is expected for this indicator.')
            if 'none' in val and indicator.allow_none:
                val = []
            else:
                for option in val:
                    valid = self.__options_valid(option, indicator)
                    if not valid:
                        raise serializers.ValidationError(f'ID {val} is not valid for indicator {indicator.name}.')
        if indicator.type == Indicator.Type.SINGLE:
            if val == 'none' and indicator.allow_none:
                val = None
            else:
                valid = self.__options_valid(option, indicator)
                if not valid:
                    raise serializers.ValidationError(f'ID {val} is not valid for indicator {indicator.name}.')
        if indicator.type == Indicator.Type.INT:
            try:
                val = int(val)
            except (TypeError, ValueError):
                raise serializers.ValidationError(f'Integer is required.')
        if indicator.type == Indicator.Type.BOOL:
            if val not in [True, False, 0, 1, "true", "false"]:
                raise serializers.ValidationError('Boolean is required.')
    
    def __should_be_visible(self, indicator, responses, respondent, task):
        logic_group = LogicGroup.objects.filter(indicator=indicator).first()
        if logic_group:
            conditions = LogicCondition.objects.filter(group=logic_group)
            if conditions.exists():
                if logic_group.group_operator == LogicGroup.Operator.AND:   
                    for condition in conditions.all():
                        passed = check_logic(c=condition, response_info=responses, assessment=task.assessment, respondent=respondent)
                        print(indicator.name, passed)
                        if not passed:
                            return False
                if logic_group.group_operator == LogicGroup.Operator.OR:   
                    for condition in conditions.all():
                        passed = check_logic(condition, responses, task.assessment, respondent)
                        if passed:
                            return True
                    return False
        return True    
    def validate(self, attrs):
        user = self.context['request'].user
        if user.role == 'client':
            raise PermissionDenied('You do not have permission to perform this action.')
        ir_date = attrs.get('interaction_date', None)
        loc = attrs.get('interaction_location', None)
        task = attrs.get('task')
        respondent = attrs.get('respondent')
        if user.role != 'admin':
            #if not an admin, only allow users to assign targets to their children
            if user.role not in ['meofficer', 'admin']:
                is_child = ProjectOrganization.objects.filter(
                    organization=task.organization,
                    parent_organization=user.organization,
                    project=task.project
                ).exists()
                if not is_child and task.organization != user.organization:
                    raise PermissionDenied('You do not have permission to create this interaction.')
            else:
                if task.organization != user.organization:
                    raise PermissionDenied('You do not have permission to create this interaction.')
        if not task.assessment:
            raise serializers.ValidationError('An assessment is required to create an interaction.')
        
        if not ir_date or not loc:
            raise serializers.ValidationError('Date and location are both required.')
        if ir_date > date.today():
            raise serializers.ValidationError('Assessment dates cannot be in the future.')
        responses = attrs.get('response_data')

        for key, item in responses.items():
            indicator = Indicator.objects.filter(id=key).first()
            if not indicator:
                raise serializers.ValidationError(f'Invalid indicator ID provided: "{key}"')
            #first check if the item should be visible
            sbv = self.__should_be_visible(indicator, responses, respondent, task)
            print(sbv)
            #then check what the value is
            val = item.get('value', None)
            #if this should be visible and the indicator is required, but there is no value, raise an error
            if sbv and val in [[], None, ''] and indicator.required:
                raise serializers.ValidationError(f'Indicator {indicator.name} is required.')
            # if this shouldn't be visible but a value was sent anyway, raise an error
            if not sbv and val not in [[], None, '']:
                raise serializers.ValidationError(f'Indicator {indicator.name} does not meet the criteria to be answered.')
            if sbv:
                print(key)
                self.__value_valid(indicator, val)
            
            
    
        return attrs
    def __make_response(self, interaction, indicator, data):
        if data.get('value') in [[], None, '']:
            return
        if indicator.type == Indicator.Type.MULTI:
            options = data.get('value')
            for option in options:
                response = Response.objects.create(
                    interaction=interaction,
                    indicator=indicator,
                    response_option_id=option,
                    response_date=data.get('date', interaction.interaction_date),
                    response_location=data.get('location', interaction.interaction_location),
                )
        else:
            boolVal = data.get('value') if indicator.type == Indicator.Type.BOOL else None
            option = data.get('value') if indicator.type == Indicator.Type.SINGLE else None
            text = data.get('value') if not boolVal and not option else None

            response = Response.objects.create(
                interaction=interaction,
                indicator=indicator,
                response_value=text,
                response_boolean=boolVal,
                response_option=option,
                response_date=data.get('date', interaction.interaction_date),
                response_location=data.get('location', interaction.interaction_location),
            )
    def create(self, validated_data):
        user = self.context['request'].user
        response_data = validated_data.pop('response_data', [])
        interaction = Interaction.objects.create(**validated_data)
        for key, data in response_data.items():
            indicator = Indicator.objects.filter(id=key).first()
            self.__make_response(interaction, indicator, data)
        interaction.created_by = user
        interaction.save()
        return interaction

    def update(self, instance, validated_data):
        user = self.context['request'].user
        response_data = validated_data.pop('response_data', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        Response.objects.filter(interaction=instance).delete()
        for key, data in response_data.items():
            indicator = Indicator.objects.filter(id=key).first()
            self.__make_response(instance, indicator, data)
        instance.updated_by = user
        instance.save()
        return instance