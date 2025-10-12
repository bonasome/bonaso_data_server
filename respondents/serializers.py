from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from datetime import date
from django.utils.timezone import now

from django.db.models import Q

from respondents.models import Respondent, Interaction, Response, Pregnancy, HIVStatus, KeyPopulation, DisabilityType, RespondentAttribute, RespondentAttributeType, KeyPopulationStatus, DisabilityStatus
from respondents.utils import update_m2m_status, respondent_flag_check,  dummy_dob_calc, calculate_age_range, check_event_perm
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
    indicator_id = serializers.PrimaryKeyRelatedField(
        source='response_option',
        queryset=Indicator.objects.all(),
        write_only=True,
        required=False, 
        allow_null=True
    )
    option_id = serializers.PrimaryKeyRelatedField(
        source='response_option',
        queryset=Option.objects.all(),
        write_only=True,
        required=False, 
        allow_null=True
    )
    class Meta:
        model=Response
        fields = [
            'id', 'response_value', 'response_option', 'response_date', 'indicator', 'option_id', 'indicator_id',
            'interaction'
        ]
    def __check_logic(self, indicator, value, respondent):
        past_responses = past_responses or {}

        # Get the logic group (assumes only one per indicator)
        group = LogicGroup.objects.filter(indicator=indicator).first()
        if not group:
            return True  # No logic = always visible / valid
        
        operator = group.operator  # AND / OR
        conditions = group.conditions.all()

        results = []

        for cond in conditions:
            st = cond.source_type
            op = cond.operator
            value = None

            # 1️⃣ Respondent field
            if st == LogicCondition.SourceType.RES:
                field_name = cond.respondent_field
                value = getattr(respondent, field_name, None)
                compare_to = cond.value_text

            # 2️⃣ Past indicator response (within this assessment)
            elif st == LogicCondition.SourceType.ASS:
                prereq_indicator = cond.prereq
                # try cache first
                value = past_responses.get(prereq_indicator.code)
                if value is None:
                    # fallback: query Response model
                    response = Response.objects.filter(
                        respondent=respondent, indicator=prereq_indicator
                    ).first()
                    value = response.value if response else None
                # For option fields, use option id
                if prereq_indicator.type in [Indicator.Type.SINGLE, Indicator.Type.MULTI] and cond.value_option:
                    compare_to = cond.value_option.id
                    if isinstance(value, Option):
                        value = value.id
                else:
                    compare_to = cond.value_text

            else:
                results.append(False)
                continue

            # 3️⃣ Compare
            if op == '=':
                results.append(value == compare_to)
            elif op == '!=':
                results.append(value != compare_to)
            elif op == '>':
                results.append(value > compare_to)
            elif op == '<':
                results.append(value < compare_to)
            elif op == 'contains':
                results.append(compare_to in (value or []))
            elif op == '!contains':
                results.append(compare_to not in (value or []))
            else:
                results.append(False)

        # Apply group operator
        if operator == 'AND':
            return all(results)
        else:  # OR
            return any(results)

    def validate(self, attrs):
        user = self.context['request'].user
        indicator_id = attrs.get('indicator_id')
        indicator = Indicator.objects.filter(id=indicator_id).first()
        if not indicator:
            raise serializers.ValidationError('A valid indicator is required')
        value = attrs.get('response_value', None)
        option = None
        if indicator.type in [Indicator.Type.SINGLE, Indicator.Type.MULTI]:
            option_id = attrs.get('option_id', None)
            option = Option.objects.filter(id=option_id).first()
            if not option or option not in Option.objects.filter(indicator=indicator).values_list('id', flat=True):
                raise serializers.ValidationError('A valid option is required')
            value = option
        if not value:
            raise serializers.ValidationError('A value is required for a response.')
        self.__check_logic(indicator, value, interaction.respondent)
        


class InteractionSerializer(serializers.ModelSerializer):
    respondent = RespondentSerializer(read_only=True)
    task = TaskSerializer(read_only=True)
    responses = serializers.SerializerMethodField()

    def get_responses(self, obj):
        responses = Response.objects.filter(interaction=obj)
        return ResponseSerializer(responses, many=True)
    
    class Meta:
        model=Interaction
        fields = [
            'id', 'interaction_date', 'interaction_location', 'comments', 'responses'
        ]

