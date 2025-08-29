from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from datetime import date
from django.utils.timezone import now

from django.db.models import Q

from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, KeyPopulation, DisabilityType, InteractionSubcategory, RespondentAttribute, RespondentAttributeType, KeyPopulationStatus, DisabilityStatus
from respondents.utils import update_m2m_status, respondent_flag_check, interaction_flag_check, dummy_dob_calc, calculate_age_range, check_event_perm
from respondents.exceptions import DuplicateExists

from projects.models import Task, ProjectOrganization
from projects.serializers import TaskSerializer

from indicators.models import IndicatorSubcategory, Indicator
from indicators.serializers import IndicatorSubcategorySerializer
from flags.serializers import FlagSerializer
from profiles.serializers import ProfileListSerializer
from events.models import Event
from events.serializers import EventSerializer
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


#reevaluate if we need this after taking another swing at the profiles serializer
class SimpleInteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model=Interaction
        fields = ['id', 'interaction_date']

    
class InteractionSubcategoryInputSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True) #to allow creation fo new 
    subcategory = IndicatorSubcategorySerializer()
    numeric_component = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    
class InteractionSerializer(serializers.ModelSerializer):
    respondent = serializers.PrimaryKeyRelatedField(queryset=Respondent.objects.all())
    task_id = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True, source='task')
    task = TaskSerializer(read_only=True)
    subcategories = serializers.SerializerMethodField()
    subcategories_data = InteractionSubcategoryInputSerializer(many=True, write_only=True, required=False)
    flags = FlagSerializer(read_only=True, many=True)
    created_by = ProfileListSerializer(read_only=True)
    updated_by = ProfileListSerializer(read_only=True)
    event = EventSerializer(read_only=True)
    event_id = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all(), write_only=True, source='event', required=False, allow_null=True)
    display_name = serializers.SerializerMethodField()
    parent_organization = serializers.SerializerMethodField() #return the id of the parent organization (if applicable) for frontend permissions checks
    
    def get_display_name(self, obj):
        return str(obj)  # Uses obj.__str__()

    def get_subcategories(self, obj):
        subcats = InteractionSubcategory.objects.filter(interaction=obj)
        data = []
        for subcat in subcats:
            data.append({
                'id': subcat.id,
                'subcategory': {
                    'id': subcat.subcategory.id,
                    'name': subcat.subcategory.name
                },
                'numeric_component': subcat.numeric_component
            })
        return data
    def get_parent_organization(self, obj):
        org = ProjectOrganization.objects.filter(organization=obj.task.organization, project=obj.task.project).first().parent_organization
        return org.id if org else None
    class Meta:
        model=Interaction
        fields = [
            'id', 'display_name', 'respondent', 'subcategories', 'subcategories_data', 'task_id', 'task',
            'interaction_date', 'numeric_component', 'created_by', 'updated_by', 'created_at', 'updated_at',
            'comments', 'interaction_location', 'event','event_id', 'flags', 'parent_organization'
        ]
    
    def to_internal_value(self, data):
        subcat = data.get('subcategories_data', None)
        if subcat == '':
            data['subcategories_data'] = []
        return super().to_internal_value(data)

    def validate(self, data):
        user = self.context['request'].user
        if user.role == 'client':
                raise PermissionDenied('You do not have permission to perform this action.')
        task = data.get('task') or getattr(self.instance, 'task', None)
        respondent = data.get('respondent') or getattr(self.instance, 'respondent', None)
        event = data.get('event') or getattr(self.instance, 'event', None)
        subcategories = data.get('subcategories_data', [])
        interaction_date = data.get('interaction_date') or getattr(self.instance, 'interaction_date', None)
        interaction_location = data.get('interaction_location') or getattr(self.instance, 'interaction_location', None)
        number = data.get('numeric_component')
        if number == '':
            number = None
        ### ===check permissions==== ###
        #clients cannot create
        if user.role == 'client':
            raise PermissionDenied("You do not have permission to make edits to interactions.")
        #admins can do whatever
        if user.role != 'admin':
            # me officers have perms over their org and their child org
            if user.role in ['meofficer', 'manager']:
                if task.organization != user.organization and not ProjectOrganization.objects.filter(project=task.project, organization=task.organization, parent_organization=user.organization).exists():
                    raise PermissionDenied(
                        "You may not create or edit interactions not related to your organization or its child organizations."
                    )
            #everyone else is limited to their own org
            else:
                if task.organization != user.organization:
                    raise PermissionDenied(
                        "You may not create or edit interactions not related to your organization."
                    )
        if event:
            if not check_event_perm(user, event, task.project.id):
                raise PermissionDenied(
                        "You may not attach an interaction to an event you are not a part of."
                    )
            
        ###===Check fields===###
        #verify date is present and not in the future or outside of the project
        if not interaction_date:
            raise serializers.ValidationError("Interaction date is required.")
        if interaction_date > date.today():
            raise serializers.ValidationError("Interaction date may not be in the future.")
        if interaction_date < task.project.start or interaction_date > task.project.end:
            raise serializers.ValidationError("This interaction is set for a date outside of the project boundaries.")
        
        #verify location is present
        if not interaction_location:
            raise serializers.ValidationError("Interaction location is required.")
        #verify that the selected task's indicator is supposed to be linked to a respondent
        if task.indicator.indicator_type != Indicator.IndicatorType.RESPONDENT:
            raise serializers.ValidationError("This task cannot be assigned to an interaction.")
        
        #check if number is required/present
        requires_number = task.indicator.require_numeric
        if requires_number and not task.indicator.subcategories.exists():
            try:
                if number in [None, '']:
                    raise ValueError
                int(number) 
            except (ValueError, TypeError):
                raise serializers.ValidationError("Task requires a valid number.")
        #make sure a number wasn't sent and raise an error if it was, since this will be ignored
        else:
            if number in ['', '0']:
                data['numeric_component'] = None
            elif number not in [None, 0, '0', '']:
                raise serializers.ValidationError("Task does not expect a number.")

        #work through subcategories if applicable
        if task.indicator.subcategories.exists():
            if not subcategories or subcategories in [None, '', []]:
                raise serializers.ValidationError("Subcategories are required for this task.")
            if task.indicator.require_numeric:
                for cat in subcategories:
                    numeric_value = cat.get('numeric_component', None)

                    if numeric_value is None:
                        raise serializers.ValidationError(
                            f"Subcategory {cat.get('subcategory').get('name')} requires a numeric component."
                        )
                    try:
                        int(numeric_value)
                    except (ValueError, TypeError):
                        raise serializers.ValidationError(
                            f"Numeric component for subcategory {cat.get('subcategory').get('name')} must be a valid integer."
                        )
        else:
            if not subcategories or subcategories in [None, '', []]:
                data['subcategories_data'] = []
    
        return data
    
    def create(self, validated_data):
        user = self.context['request'].user
        respondent = validated_data.pop('respondent', None) or self.context.get('respondent')
        subcategories = validated_data.pop('subcategories_data', [])

        # Create the interaction
        interaction = Interaction.objects.create(
            respondent=respondent,
            created_by=user,
            **validated_data
        )
        for subcat in subcategories:
            subcat_id = subcat.get('subcategory').get('id')
            numeric_value = None
            if interaction.task.indicator.require_numeric:
                numeric_value = int(subcat.get('numeric_component'))
            

            try:
                subcategory = IndicatorSubcategory.objects.get(pk=subcat_id)
            except IndicatorSubcategory.DoesNotExist:
                raise serializers.ValidationError(f"Subcategory with id {subcat_id} not found.")

            InteractionSubcategory.objects.create(
                interaction=interaction,
                subcategory=subcategory,
                numeric_component=numeric_value
            )
        
        #check interaction for any flags --> see respondents.utils.interaction_flag_check for more details
        interaction_flag_check(interaction, user, downstream=False)

        #possible that edits to a parent may cause a child to flag or unflag, so verify them as well
        dependent_tasks = Task.objects.filter(indicator__prerequisites=interaction.task.indicator)
        downstream = Interaction.objects.filter(
            respondent=interaction.respondent,
            task__in=dependent_tasks,
        )
        for ir in downstream:
            print('running downstream for ', ir.task.indicator.name )
            interaction_flag_check(ir, user, downstream=True)
            ir.save()

        return interaction
    
    def update(self, instance, validated_data):
        user = self.context['request'].user
        created_by = instance.created_by
        #perms are verified, but for updates we add the special perm that lower roles can only edit their own interactions
        if user.role not in ['meofficer', 'manager', 'admin']:
            if instance.created_by != user:
                raise PermissionDenied("You may only edit your interactions.")
        
        subcategories = validated_data.pop('subcategories_data', [])
        if instance.task.indicator.subcategories.exists():
            if subcategories not in ['', [], None]:
                InteractionSubcategory.objects.filter(interaction=instance).delete()

                for subcat in subcategories:
                    subcat_id = subcat.get('subcategory').get('id')
                    numeric_value = None
                    if instance.task.indicator.require_numeric:
                        numeric_value = subcat.get('numeric_component', None)

                    try:
                        subcategory = IndicatorSubcategory.objects.get(pk=subcat_id)
                    except IndicatorSubcategory.DoesNotExist:
                        raise serializers.ValidationError(f"Subcategory with id {subcat_id} not found.")

                    InteractionSubcategory.objects.create(
                        interaction=instance,
                        subcategory=subcategory,
                        numeric_component=numeric_value
                    )
            else:
                raise serializers.ValidationError(f'Subcategories are required for this interaction.')
            
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.updated_by = user
        instance.save()

        #check interaction for any flags --> see respondents.utils.interaction_flag_check for more details
        interaction_flag_check(instance, user, downstream=False)

        #possible that edits to a parent may cause a child to flag or unflag, so verify them as well
        dependent_tasks = Task.objects.filter(indicator__prerequisites=instance.task.indicator)
        downstream = Interaction.objects.filter(
            respondent=instance.respondent,
            task__in=dependent_tasks,
        )
        for ir in downstream:
            print('running downstream for ', ir.task.indicator.name )
            interaction_flag_check(ir, user, downstream=True)
            ir.save()

        return instance