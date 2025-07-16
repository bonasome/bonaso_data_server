from rest_framework import serializers
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, KeyPopulation, DisabilityType, InteractionSubcategory, RespondentAttribute, RespondentAttributeType, KeyPopulationStatus, DisabilityStatus, InteractionFlag
from respondents.exceptions import DuplicateExists
from projects.models import Task, Target
from projects.serializers import TaskSerializer
from indicators.models import IndicatorSubcategory
from indicators.serializers import IndicatorSubcategorySerializer
from datetime import datetime, date
from django.db.models.functions import Abs
from django.db.models import Q, F, ExpressionWrapper, IntegerField
from rest_framework.exceptions import PermissionDenied
from django.contrib.auth import get_user_model
from respondents.utils import update_m2m_status, auto_flag_logic


User = get_user_model()

class RespondentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Respondent
        fields = ['id', 'uuid', 'is_anonymous', 'first_name', 'last_name', 'sex', 
                  'village', 'district', 'citizenship', 'comments']

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
    class Meta:
        model = Pregnancy
        fields = ['id', 'term_began', 'term_ended']

class HIVStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = HIVStatus
        fields = ['id', 'hiv_positive', 'date_positive']

class RespondentSerializer(serializers.ModelSerializer):
    id_no = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)
    dob = serializers.DateField(required=False, allow_null=True)
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()
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
    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "first_name": obj.created_by.first_name,
                "last_name": obj.created_by.last_name,
            }

    def get_updated_by(self, obj):
        if obj.updated_by:
            return {
                "id": obj.updated_by.id,
                "username": obj.updated_by.username,
                "first_name": obj.updated_by.first_name,
                "last_name": obj.updated_by.last_name,
            }
        
    class Meta:
        model=Respondent
        fields = [
            'id','id_no', 'uuid', 'is_anonymous', 'first_name', 'last_name', 'sex', 'ward',
            'village', 'district', 'citizenship', 'comments', 'email', 'phone_number', 'dob',
            'age_range', 'created_by', 'updated_by', 'created_at', 'updated_at', 'special_attribute', 
            'special_attribute_names', 'pregnancies', 'pregnancy_data', 'hiv_status', 'kp_status', 'kp_status_names', 'disability_status',
            'disability_status_names', 'hiv_status_data'
        ]

    def validate(self, attrs):
        user = self.context['request'].user
        role = getattr(user, 'role', None)
        respondent = self.instance
        if role == 'client':
            raise PermissionDenied("You do not have permission to make edits to interactions.")
        if attrs.get('is_anonymous'):
            for field in ['first_name', 'last_name', 'email', 'phone_number', 'id_no', 'dob']:
                if attrs.get(field):
                    raise serializers.ValidationError(f"{field} must not be set when is_anonymous is True.")
        id_no = attrs.get('id_no')
        if id_no:
            if self.instance:
                existing = Respondent.objects.filter(id_no=id_no).exclude(id=self.instance.id)
            else:
                existing = Respondent.objects.filter(id_no=id_no)
            if existing.exists():
                raise DuplicateExists(
                    detail="This respondent already exists.",
                    existing_id=existing.first().id
                )
        
        dob = attrs.get('dob')
        if dob and dob > date.today():
            raise serializers.ValidationError('Date of Birth may not be in the future.')
        pregnancies = attrs.get('pregnancy_data')
        if pregnancies:
            for pregnancy in pregnancies:
                term_began = pregnancy.get('term_began', None)
                term_ended = pregnancy.get('term_ended', None)
                if not term_began and not term_ended:
                    continue
                if not term_began:
                    raise serializers.ValidationError("Pregnancy term start date is required.")
                if term_ended and term_began > term_ended:
                    raise serializers.ValidationError('Pregnancy term start must be after the end')
                if term_began > date.today() or (term_ended and term_ended > date.today()):
                    raise serializers.ValidationError('Pregnancy dates cannot be in the future.')
                base_qs = Pregnancy.objects.filter(respondent=respondent)

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
                
        hiv_status_data = attrs.get('hiv_status_data')
        if hiv_status_data:
            date_positive = hiv_status_data.get('date_positive', None)
            if not date_positive:
                date_positive = date.today()
            if date_positive > date.today():
                    raise serializers.ValidationError('Date Positive cannot be in the future.')
        return attrs
    
    def validate_required_attribute_names(self, value):
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
        valid_choices = set(choice[0] for choice in KeyPopulation.KeyPopulations.choices)
        cleaned = []

        for name in value:
            if name not in valid_choices:
                raise serializers.ValidationError(f"{name} is not a valid attribute.")
            cleaned.append(name)
        return cleaned
    
    def validate_disability_status_names(self, value):
        valid_choices = set(choice[0] for choice in DisabilityType.DisabilityTypes.choices)
        cleaned = []

        for name in value:
            if name not in valid_choices:
                raise serializers.ValidationError(f"{name} is not a valid attribute.")
            cleaned.append(name)
        return cleaned
    
    def create(self, validated_data):
        special_attribute_names = validated_data.pop('special_attribute_names', [])
        kp_status_names = validated_data.pop('kp_status_names', [])
        disability_status_names = validated_data.pop('disability_status_names', [])
        pregnancies = validated_data.pop('pregnancy_data', [])
        hiv_status_data = validated_data.pop('hiv_status_data', None)
        
        respondent = Respondent.objects.create(**validated_data)
        
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

        # For Disability
        
        disability_instances = update_m2m_status(
            model=DisabilityType,
            through_model=DisabilityStatus,
            respondent=respondent,
            name_list=disability_status_names,
            related_field='disability'
        )
        respondent.disability_status.set(disability_instances)

        
        if hiv_status_data:
            hiv_positive = hiv_status_data.get('hiv_positive', None)
            if hiv_positive:
                hiv_positive = True if hiv_positive in ['true', 'True', True, '1'] else None
                if hiv_positive:
                    date_positive = hiv_status_data.get('date_positive')
                    if not date_positive:
                        date_positive = date.today()
                    HIVStatus.objects.create(respondent=respondent, hiv_positive=hiv_positive, date_positive=date_positive)

        
        for pregnancy in pregnancies:
            term_began = pregnancy.get('term_began', None)
            term_ended = pregnancy.get('term_ended', None)
            if term_began:
                is_pregnant =  term_began and not term_ended
                Pregnancy.objects.create(respondent=respondent, is_pregnant=is_pregnant, term_began=term_began, term_ended=term_ended)

        return respondent

    def update(self, instance, validated_data):
        kp_status_names = validated_data.pop('kp_status_names', [])
        disability_status_names = validated_data.pop('disability_status_names', [])
        pregnancies = validated_data.pop('pregnancy_data', [])
        hiv_status_data = validated_data.pop('hiv_status_data', None)
        instance = super().update(instance, validated_data)

        special_attribute_names = validated_data.pop('special_attribute_names', [])
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

        
        kp_instances = update_m2m_status(
            model=KeyPopulation,
            through_model=KeyPopulationStatus,
            respondent=instance,
            name_list=kp_status_names,
            related_field='key_population'
        )
        instance.kp_status.set(kp_instances)

        # For Disability
        
        disability_instances = update_m2m_status(
            model=DisabilityType,
            through_model=DisabilityStatus,
            respondent=instance,
            name_list=disability_status_names,
            related_field='disability'
        )
        instance.disability_status.set(disability_instances)

        if hiv_status_data:
            print(hiv_status_data)
            hiv_positive = hiv_status_data.get('hiv_positive', None)
            if hiv_positive is not None:
                hiv_positive = True if hiv_positive in ['true', 'True', True, '1'] else False
                if hiv_positive:
                    date_positive = hiv_status_data.get('date_positive')
                    if not date_positive:
                        date_positive = date.today()
                existing = HIVStatus.objects.filter(respondent=instance).first()
                if existing:
                    existing.hiv_positive = hiv_positive
                    existing.date_positive = date_positive if hiv_positive else None
                    existing.save()
                else:
                        HIVStatus.objects.create(respondent=instance, hiv_positive=hiv_positive, date_positive=date_positive)

        
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
                    pregnancy.save()
                except Pregnancy.DoesNotExist:
                    raise serializers.ValidationError(f"Invalid pregnancy ID: {pid}")
            else:
                if term_began:
                    Pregnancy.objects.create(respondent=instance, is_pregnant=is_pregnant, term_began=term_began, term_ended=term_ended)
            
        if instance.is_anonymous:
            instance.first_name = None
            instance.dob = None
            instance.ward = None
            instance.id_no = None
            instance.email = None
            instance.phone_number = None
            instance.save()

        return instance

class SimpleInteractionSerializer(serializers.ModelSerializer):
    class Meta:
        model=Interaction
        fields = [
            'id', 'interaction_date'
        ]

class InteractionSubcategoryInputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    numeric_component = serializers.IntegerField(required=False, allow_null=True)

class InteractionSubcategoryOutputSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='subcategory.id')
    name = serializers.CharField(source='subcategory.name')

    class Meta:
        model = InteractionSubcategory
        fields = ['id', 'name', 'numeric_component']

class InteractionFlagSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()
    resolved_by = serializers.SerializerMethodField()
    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "first_name": obj.created_by.first_name,
                "last_name": obj.created_by.last_name,
            }
        return None
    def get_resolved_by(self, obj):
        if obj.resolved_by:
            return {
                "id": obj.resolved_by.id,
                "username": obj.resolved_by.username,
                "first_name": obj.resolved_by.first_name,
                "last_name": obj.resolved_by.last_name,
            }
        return None
    
    class Meta:
        model=InteractionFlag
        fields = [
            'id', 'reason', 'auto_flagged', 'created_by', 'created_at', 'resolved', 'auto_resolved',
            'resolved_reason', 'resolved_by', 'resolved_at'
        ]

class InteractionSerializer(serializers.ModelSerializer):
    respondent = serializers.PrimaryKeyRelatedField(queryset=Respondent.objects.all())
    task = serializers.PrimaryKeyRelatedField(queryset=Task.objects.all(), write_only=True)
    task_detail = TaskSerializer(source='task', read_only=True)
    subcategories = serializers.SerializerMethodField()
    subcategories_data = InteractionSubcategoryInputSerializer(many=True, write_only=True, required=False)
    flags = InteractionFlagSerializer(read_only=True, many=True)
    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()

    def get_subcategories(self, obj):
        interaction_subcats = InteractionSubcategory.objects.filter(interaction=obj)
        return InteractionSubcategoryOutputSerializer(interaction_subcats, many=True).data
    
    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "first_name": obj.created_by.first_name,
                "last_name": obj.created_by.last_name,
            }

    def get_updated_by(self, obj):
        if obj.updated_by:
            return {
                "id": obj.updated_by.id,
                "username": obj.updated_by.username,
                "first_name": obj.updated_by.first_name,
                "last_name": obj.updated_by.last_name,
            }
    class Meta:
        model=Interaction
        fields = [
            'id', 'respondent', 'subcategories', 'subcategories_data', 'task', 'task_detail',
            'interaction_date', 'numeric_component', 'created_by', 'updated_by', 'created_at', 'updated_at',
            'comments', 'interaction_location', 'flags'
        ]
    
    def to_internal_value(self, data):
        subcat = data.get('subcategories_data', None)
        if subcat == '':
            data['subcategories_data'] = []
        return super().to_internal_value(data)

    def validate(self, data):
        from organizations.models import Organization
        user = self.context['request'].user
        if user.role == 'client':
                raise PermissionDenied('You do not have permission to perform this action.')
        task = data.get('task') or getattr(self.instance, 'task', None)
        respondent = data.get('respondent') or getattr(self.instance, 'respondent', None)
        subcategories = data.get('subcategories_data', [])
        interaction_date = data.get('interaction_date') or getattr(self.instance, 'interaction_date', None)
        number = data.get('numeric_component')
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)

        if role == 'client':
            raise PermissionDenied("You do not have permission to make edits to interactions.")
        if role != 'admin':
            if not org:
                raise PermissionDenied("User must belong to an organization.")

            # Ensure the task is part of the user's org or child orgs
            if role in ['meofficer', 'manager']:
                allowed_org_ids = Organization.objects.filter(
                    Q(parent_organization=org) | Q(id=org.id)
                ).values_list('id', flat=True)
            else:
                allowed_org_ids = [org.id]

            if task.organization_id not in allowed_org_ids:
                raise PermissionDenied(
                    "You may not create or edit interactions not related to your organization or its child organizations."
                )
    
        if not interaction_date:
            raise serializers.ValidationError("Interaction date is required.")
        #parsed_date = datetime.fromisoformat(interaction_date).date()
        if interaction_date > date.today():
            raise serializers.ValidationError("Interaction date may not be in the future.")
        if interaction_date < task.project.start or interaction_date > task.project.end:
            raise serializers.ValidationError("This interaction is set for a date outside of the project boundaries.")
        
        if task.indicator.indicator_type != 'Respondent':
            raise serializers.ValidationError("This task cannot be assigned to an interaction.")
        requires_number = task.indicator.require_numeric
        if requires_number and not task.indicator.subcategories.exists():
            try:
                if number in [None, '']:
                    raise ValueError
                int(number) 
            except (ValueError, TypeError):
                raise serializers.ValidationError("Task requires a valid number.")
        else:
            if number in ['', '0']:
                data['numeric_component'] = None
            elif number not in [None, 0, '0']:
                raise serializers.ValidationError("Task does not expect a number.")

        if task.indicator.subcategories.exists():
            print(task.indicator.subcategories)
            if not subcategories or subcategories in [None, '', []]:
                raise serializers.ValidationError("Subcategories are required for this task.")
            if task.indicator.require_numeric:
                for cat in subcategories:
                    print(cat)
                    numeric_value = cat.get('numeric_component', None)

                    if numeric_value is None:
                        raise serializers.ValidationError(
                            f"Subcategory {cat.get('name')} requires a numeric component."
                        )
                    try:
                        int(numeric_value)
                    except (ValueError, TypeError):
                        raise serializers.ValidationError(
                            f"Numeric component for subcategory {cat.get('name')} must be a valid integer."
                        )
        else:
            if not subcategories or subcategories in [None, '', []]:
                data['subcategories_data'] = []

        required_attributes = task.indicator.required_attribute.all()
        
        if required_attributes.exists():
            respondent_attrs = set(respondent.special_attribute.values_list('id', flat=True))
            for attribute in required_attributes:
                if attribute.id not in respondent_attrs:
                    raise serializers.ValidationError(
                        f"This task requires that the respondent be a {attribute.name}."
                    )
        return data
    
    def validate_interaction_date(self, value):
        if not value:
            raise serializers.ValidationError('Date is required.')
        return value
    
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
            subcat_id = subcat['id']
            numeric_value = subcat.get('numeric_component')

            try:
                subcategory = IndicatorSubcategory.objects.get(pk=subcat_id)
            except IndicatorSubcategory.DoesNotExist:
                raise serializers.ValidationError(f"Subcategory with id {subcat_id} not found.")

            InteractionSubcategory.objects.create(
                interaction=interaction,
                subcategory=subcategory,
                numeric_component=numeric_value
            )
        #auto flag does not need to run if the interaction has been manually marked OK or manually flagged for another reason
        auto_flag_logic(interaction, downstream=False)
        dependent_tasks = Task.objects.filter(indicator__prerequisites=interaction.task.indicator)
        #possible that edits to a parent may cause a child to flag or unflag, so verify them as well
        #but only check if no one manually flagged it or manually marked it as ok
        downstream = Interaction.objects.filter(
            respondent=interaction.respondent,
            task__in=dependent_tasks,
        )
        for ir in downstream:
            print('running downstream for ', ir.task.indicator.name )
            auto_flag_logic(ir, downstream=True)
            ir.save()
        return interaction
    
    def update(self, instance, validated_data):
        user = self.context['request'].user
        created_by = instance.created_by
        if user.role not in ['meofficer', 'manager', 'admin']:
            if instance.created_by != user:
                raise PermissionDenied("You may only edit your interactions.")
        subcategories = validated_data.pop('subcategories_data', [])
        if instance.task.indicator.subcategories.exists():
            if subcategories not in ['', [], None]:
                InteractionSubcategory.objects.filter(interaction=instance).delete()

                for subcat in subcategories:
                    subcat_id = subcat['id']
                    numeric_value = subcat.get('numeric_component')

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

        auto_flag_logic(instance, downstream=False)
        dependent_tasks = Task.objects.filter(indicator__prerequisites=instance.task.indicator)
        #possible that edits to a parent may cause a child to flag or unflag, so verify them as well
        #but only check if no one manually flagged it or manually marked it as ok
        downstream = Interaction.objects.filter(
            respondent=instance.respondent,
            task__in=dependent_tasks,
        )
        for ir in downstream:
            print('running downstream for ', ir.task.indicator.name )
            auto_flag_logic(ir, downstream=True)
            ir.save()

        return instance