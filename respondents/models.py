from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from users.models import User
from indicators.models import Indicator, IndicatorSubcategory
from projects.models import Project, Task
from datetime import datetime, date
import uuid

class Respondent(models.Model):
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

    class AgeRanges(models.TextChoices):
        U18 = 'under_18', _('Under 18')
        ET_24 = '18_24', _('18–24')
        T5_34 = '25_34', _('25–34')
        T5_44 = '35_44', _('35–44')
        F5_64 = '45_64', _('45–64')
        O65 = '65_plus', _('65+')

    is_anonymous = models.BooleanField(default=False)
    comments = models.TextField(blank=True)
    uuid =  models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    age_range = models.CharField(max_length=10, choices=AgeRanges.choices, blank=True, null=True, verbose_name='Age Range')

    id_no = models.CharField(max_length=255, unique=True, verbose_name='ID/Passport Number', blank=True, null=True)
    first_name = models.CharField(max_length=255, verbose_name='First Name', blank=True, null=True)
    last_name = models.CharField(max_length=255, verbose_name='Last Name', blank=True, null=True)
    dob = models.DateField(verbose_name='Date of Birth', blank=True, null=True)
    sex = models.CharField(max_length=2, choices=Sex.choices, verbose_name='Sex')
    ward = models.CharField(max_length=255, verbose_name='Ward', blank=True, null=True)
    village = models.CharField(max_length=255, verbose_name='Village')
    district = models.CharField(max_length=25, choices=District.choices, verbose_name='District')
    citizenship = models.CharField(max_length=255, verbose_name='Citizenship/Nationality')

    email = models.EmailField(verbose_name='Email Address', null=True, blank=True)
    phone_number = models.CharField(max_length=255, verbose_name='Phone Number', null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_DEFAULT, default=None, null=True, blank=True)

    def clean(self):
        if self.is_anonymous:
            if self.first_name or self.last_name or self.email or self.phone_number or self.id_no:
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

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'
    
    def get_age(self):
        today = datetime.today()
        return today.year - self.dob.year - ((today.month, today.day) < (self.dob.month, self.dob.day))
    
    def get_age_range(self):
        if not self.age_range and self.dob:
            age = self.get_age()
            if age < 18:
                ageRange = self.AgeRanges.U18
            elif age < 25:
                ageRange = self.AgeRanges.ET_24
            elif age < 35:
                ageRange = self.AgeRanges.T5_34
            elif age < 45:
                ageRange = self.AgeRanges.T5_44
            elif age < 65:
                ageRange = self.AgeRanges.F5_64
            elif age > 65:
                ageRange = self.AgeRanges.O65
            return ageRange

    def __str__(self):
        return self.get_full_name() if not self.is_anonymous else f'Anonymous Respondent ({self.uuid})'

class KeyPopulationStatus(models.Model):
    class KeyPopulations(models.TextChoices):
        FSW = 'FSW', _('Female Sex Workers')
        MSM = 'MSM', _('Men Who Have Sex With Men')
        PWID = 'PWID', _('People Who Inject Drugs')
        TG = 'TG', _('Transgender')
        INTERSEX = 'INTERSEX', _('Intersex')
        LBQ = 'LBQ', _('Lesbian, Bisexual, or Queer')
        OTHER = 'OTHER', _('Other Key Population Status')
    
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE)
    kp_status = models.CharField(max_length=10, choices=KeyPopulations.choices, blank=True, null=True, verbose_name='Key Population Status')

    def __str__(self):
        return f'{self.respondent}: {self.kp_status}'
class Pregnancy(models.Model):
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE)
    is_pregnant = models.BooleanField()
    term_began = models.DateField()
    term_ended = models.DateField(null=True, blank=True)

class HIVStatus(models.Model):
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE)
    hiv_positive = models.BooleanField()
    date_positive = models.DateField()

class Interaction(models.Model):
    respondent = models.ForeignKey(Respondent, on_delete=models.PROTECT)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, blank=True, null=True)
    interaction_date = models.DateField()
    subcategory = models.ForeignKey(IndicatorSubcategory, on_delete=models.PROTECT, blank=True, null=True)
    prerequisite = models.ForeignKey('self', on_delete=models.PROTECT, blank=True, null=True, related_name='prerequisite_interaction')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_DEFAULT, default=None, null=True, blank=True)

    def __str__(self):
        return f'Interaction with {self.respondent} on {self.interaction_date} for {self.task.indicator.code} ({self.task.project.name})'