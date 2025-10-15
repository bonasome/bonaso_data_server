from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericRelation
from datetime import date
import uuid

from django.contrib.auth import get_user_model
User = get_user_model()
from indicators.models import Option, Indicator
from projects.models import Task
from events.models import Event

'''
The respondent model relies on a variety of TextChoices. These are both used to control inputs but also
are used during analysis for demographic splits. 
'''


class DisabilityType(models.Model):
    '''
    Helper model to keep track of multi-select disability statuses.
    '''
    class DisabilityTypes(models.TextChoices):
        VI = 'VI', _('Visually Impaired')
        PD = 'PD', _('Physical Disability')
        ID = 'ID', _('Intellectual Disability')
        HI = 'HI', _('Hearing Impaired')
        PSY = 'PSY', _('Psychiatric Disability')
        SI = 'SI', _('Speech Impaired')
        OTHER = 'OTHER', _('Other Disability')
    
    name = models.CharField(max_length=10, choices=DisabilityTypes.choices, unique=True)

class KeyPopulation(models.Model):
    '''
    Helper model to keep track of multi-select key-population statuses.
    '''
    class KeyPopulations(models.TextChoices):
        FSW = 'FSW', _('Female Sex Workers')
        MSM = 'MSM', _('Men Who Have Sex With Men')
        PWID = 'PWID', _('People Who Inject Drugs')
        TG = 'TG', _('Transgender')
        INTERSEX = 'INTERSEX', _('Intersex')
        LBQ = 'LBQ', _('Lesbian Bisexual or Queer')
        OTHER = 'OTHER', _('Other Key Population Status')
    
    name = models.CharField(max_length=10, choices=KeyPopulations.choices, unique=True)

class RespondentAttributeType(models.Model):
    '''
    Respondent Attributes are kind of a catch all that is used to track certain information centrally and run easier checks.
    This way, we can do things like set an indicator to see if a person is HIV positive or a KP and run the 
    check in a centralized location. Since respondents can have mutliple attributes, this is a helper model to 
    manage that.
    '''
    class Attributes(models.TextChoices):
        PLWHIV = 'PLWHIV', _('Person Living with HIV') #auto generated
        PWD = 'PWD', _('Person Living with a Disability') #auto generated
        KP = 'KP', _('Key Population') #auto generated
        COMMUNITY_LEADER = 'community_leader', _('Community Leader')
        CHW = 'CHW', _('Community Health Worker')
        STAFF = 'staff', _('Organization Staff')

    name = models.CharField(max_length=25, choices=Attributes.choices, unique=True)
    def __str__(self):
        return self.name

class Respondent(models.Model):
    '''
    Model that's basically used to centrally store demographic information attached to interactions
    and help us better organize how that data is viewed/analyzed. Ideally, almost all indicators
    are tied directly to respondent.

    Respondents can be anonymous, in which case we require:
        1) Age Range
        2) Sex
        3) Village (or town or whatever)
        4)District
        5) Citizenship
            - We will automatically wipe any dob/id/email/phones/ward/plot_no in the serialization process.
                (these could all be considered PII)
            - We also track a uuid, which is kind of a reference for anonymous respondents.
    Otherwise, all fields are required except for Email and Phone Number (optional), and Age Range (which 
    we can calcualte from DOB).
    '''

    '''
    If you change/add any model fields, reflect those changes in the events/models.py --> DemographicCounts
    and check the analysis/views.py and analysis/utils for updating params.
    '''
    class Sex(models.TextChoices):
        FEMALE = 'F', _('Female')
        MALE = 'M', _('Male')
        NON_BINARY = 'NB', _('Non-Binary')
    class District(models.TextChoices):
        CENTRAL = 'Central', _('Central District')
        GHANZI = 'Ghanzi', _('Ghanzi District')
        KGALAGADI = 'Kgalagadi', _('Kgalagadi District')
        KGATLENG = 'Kgatleng', _('Kgatleng District')
        KWENENG = 'Kweneng', _('Kweneng District')
        NE = 'North East', _('North East District')
        NW = 'North West', _('North West District')
        SE = 'South East', _('South East District')
        SOUTHERN = 'Southern', _('Southern District')
        CHOBE = 'Chobe', _('Chobe District')
        GG = 'Gaborone', _('Greater Gaborone Area')
        GF = 'Francistown', _('Greater Francistown Area')

    class AgeRanges(models.TextChoices):
        U1 = 'under_1', _('Less Than One Year Old')
        O_4 = '1_4', _('1-4')
        F_9 = '5_9', _('5-9')
        T_14 = '10_14', _('10-14')
        FT_19 = '15_19', _('15-19')
        T_24 = '20_24', _('20–24')
        T4_29 = '25_29', _('25–29')
        TH_34 = '30_34', _('30–34')
        T5_39 = '35_39', _('35–39')
        F0_44 = '40_44', _('40-44')
        F5_49 = '45_49', _('45–49')
        FF_55 = '50_54', _('50-54')
        F4_59 = '55_59', _('55-59')
        S0_64 = '60_64', _('60-64')
        O65 = '65_plus', _('65+')
        
    uuid =  models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    is_anonymous = models.BooleanField(default=False, verbose_name='Is Anonymous')
    id_no = models.CharField(max_length=255, verbose_name='ID/Passport Number', blank=True, null=True)
    first_name = models.CharField(max_length=255, verbose_name='First Name', blank=True, null=True)
    last_name = models.CharField(max_length=255, verbose_name='Last Name', blank=True, null=True)
    age_range = models.CharField(max_length=10, choices=AgeRanges.choices, blank=True, null=True, verbose_name='Age Range')
    dob = models.DateField(verbose_name='Date of Birth', blank=True, null=True)
    dummy_dob = models.DateField(verbose_name='Estimated DOB from Age Range', blank=True, null=True)
    sex = models.CharField(max_length=2, choices=Sex.choices, verbose_name='Sex')
    plot_no = models.TextField(verbose_name='Plot Number', blank=True, null=True)
    ward = models.CharField(max_length=255, verbose_name='Ward', blank=True, null=True)
    village = models.CharField(max_length=255, verbose_name='Village')
    district = models.CharField(max_length=25, choices=District.choices, verbose_name='District')
    '''
    CITIZENSHIP:
    For similicity, this is a text field but the frontend will expect the 2 digit country code (ex. 'BW').
    This field's only use in the codebase is checking if it equals 'BW' for creating 'Is Citizen' boolean.
    If for some reason you change this field, references to ='BW' are hardcoded into
        - respondents/serializers --> RespondentSerializer (the create and update check for citizenship 
         when validating ids)
        - respondents/interaction_viewset --> InteractionViewSet --> post_template will set to BW by default
        - analysis/utils/collection (for filtering citizen vs. non-citizen)
        -analysus/utils/interactions_prep --> build_keys (for creating citizenship boolean).
    '''
    citizenship = models.CharField(max_length=255, verbose_name='Citizenship/Nationality') 
    special_attribute = models.ManyToManyField(RespondentAttributeType, through='RespondentAttribute', blank=True, verbose_name='Special Respondent Attributes')
    kp_status = models.ManyToManyField(KeyPopulation, through='KeyPopulationStatus', blank=True, verbose_name='Key Population Status')
    disability_status = models.ManyToManyField(DisabilityType, through='DisabilityStatus', blank=True, verbose_name='Disability Status')
    email = models.EmailField(verbose_name='Email Address', null=True, blank=True)
    phone_number = models.CharField(max_length=255, verbose_name='Phone Number', null=True, blank=True)
    comments = models.TextField(blank=True, null=True, verbose_name='Comments')
    
    flags = GenericRelation('flags.Flag', related_query_name='flags')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='respondent_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='respondent_updated_by')

    

    def clean(self):
        '''
        Quick verification to make sure no fields are missing or present based on the is_anonymous field.
        '''
        if self.is_anonymous:
            if self.first_name or self.last_name or self.email or self.phone_number or self.id_no or self.dob:
                raise ValidationError('This respondent was marked as anonymous, but personal information was provided. Please either remove this information or get permission from the respondent to collect their personal information.')
            if not self.age_range:
                raise ValidationError('Anonymous respondents are required to provide an age range for reporting purposes.')
        
        if not self.is_anonymous:
            missing = []
            if not self.id_no: 
                missing.append('Passport/ID Number')
            if not self.first_name: 
                missing.append('First Name')
            if not self.last_name: 
                missing.append('Last Name')
            if not self.ward: 
                missing.append('Ward')
            if not self.dob:
                missing.append('Date of Birth')
            if missing:
                raise ValidationError({field: "This field is required If the respondent does not wish to provide any of this information, please mark them as anonymous." for field in missing})


    @property
    def effective_dob(self):
        '''
        Get the DOB (preferable), or if not provided, the dummy calculated from the midpoint of the provided
        age range. Not an exact science, but its better than data becoming completely obselete every few years.
        '''
        return self.dob or self.dummy_dob

    @property
    def current_age_range(self):
        '''
        Get age range based on either DOB or effective DOB. This is used in the front end to display age ranges.
        '''
        dob = self.effective_dob
        if not dob:
            return None
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return self.calculate_age_range(age)
    
            
    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'

    def __str__(self):
        return self.get_full_name() if not self.is_anonymous else f'Anonymous Respondent ({self.uuid})'

class RespondentAttribute(models.Model):
    '''
    Through table for respondent attributes.
    '''
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE, blank=True, null=True)
    attribute = models.ForeignKey(RespondentAttributeType, on_delete=models.CASCADE, blank=True, null=True)
    auto_assigned = models.BooleanField(default=False)
    class Meta:
        unique_together = ('respondent', 'attribute')

    def __str__(self):
        return f'{self.respondent} - {self.attribute}'

class KeyPopulationStatus(models.Model):
    '''
    Through table for KP statuses.
    '''
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE, blank=True, null=True)
    key_population = models.ForeignKey(KeyPopulation, on_delete=models.CASCADE, blank=True, null=True)
    class Meta:
        unique_together = ('respondent', 'key_population')

    def __str__(self):
        return f'{self.respondent} - {self.key_population}'

class DisabilityStatus(models.Model):
    '''
    Through table for disability statuses.
    '''
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE, blank=True, null=True)
    disability = models.ForeignKey(DisabilityType, on_delete=models.CASCADE, blank=True, null=True)
    class Meta:
        unique_together = ('respondent', 'disability')

    def __str__(self):
        return f'{self.respondent} - {self.disability}'

class Pregnancy(models.Model):
    '''
    Since we can have multiple pregnancies per respondent, we need to track this seperately. We don't really
    do much with this currently, just return a bool if an interaction date is between term began and term ended.
    '''

    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE)
    is_pregnant = models.BooleanField(null=True, blank=True)
    term_began = models.DateField(null=True, blank=True)
    term_ended = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='pregnancy_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='pregnancy_updated_by')

class HIVStatus(models.Model):
    '''
    This could have been a direct field on the respondent model, but splitting it allows for us to also track
    who created/updated HIV statuses when and where. 

    Because you know, that's kind of our thing. If you weren't aware. 
    '''
    respondent = models.OneToOneField(Respondent, on_delete=models.CASCADE)
    hiv_positive = models.BooleanField(null=True, blank=True)
    date_positive = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='hiv_status_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='hiv_status_updated_by')

class Interaction(models.Model):
    respondent = models.ForeignKey(Respondent, on_delete=models.PROTECT)
    task = models.ForeignKey(Task, on_delete=models.PROTECT)
    comments = models.TextField(null=True, blank=True)
    interaction_date = models.DateField()
    interaction_location = models.CharField(max_length=255, null=True, blank=True, verbose_name='Interaction Location')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='interaction_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='interaction_updated_by')

class Response(models.Model):
    interaction = models.ForeignKey(Interaction, on_delete=models.PROTECT)
    indicator = models.ForeignKey(Indicator, on_delete=models.PROTECT)
    response_value = models.CharField(max_length=255, blank=True, null=True)
    response_option = models.ForeignKey(Option, on_delete=models.PROTECT, blank=True, null=True)
    response_boolean = models.BooleanField(blank=True, null=True)
    response_date = models.DateField(null=True, blank=True)
    response_location = models.TextField(null=True, blank=True)
