from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from organizations.models import Organization
from indicators.models import IndicatorSubcategory
from projects.models import Task

User = get_user_model()

class Event(models.Model):
    class EventType(models.TextChoices):
        TRAINING = 'Training', _('Training') 
        ACTIVITY = 'Activity', _('Activity')
        ENGAGEMENT = 'Engagement', _('Engagement')
    name = models.CharField(max_length=255, verbose_name='Event Name')
    description = models.TextField(verbose_name='Description of Event', blank=True, null=True)
    event_type = models.CharField(max_length=25, choices=EventType.choices, default=EventType.TRAINING, verbose_name='Event Type')
    host = models.ForeignKey(Organization, verbose_name='Hosting Organization', on_delete=models.SET_NULL, blank=True, null=True, related_name='host')
    organizations = models.ManyToManyField(Organization, through='EventOrganization', blank=True)
    tasks = models.ManyToManyField(Task, through='EventTask', blank=True)
    location = models.CharField(max_length=255, verbose_name='Event Location')
    event_date = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='event_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='event_updated_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class EventOrganization(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)

class EventTask(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)


class DemographicCount(models.Model):
    class Sex(models.TextChoices):
        FEMALE = 'F', _('Female')
        MALE = 'M', _('Male')
        NON_BINARY = 'NB', _('Non-Binary')

    class Status(models.TextChoices):
        STAFF = 'Staff', _('Staff')
        COMMUNITY_LEADER = 'Community_leader', _('Community Leader')
        CHW = 'CHW', _('Community Health Worker')

    class KeyPopulationType(models.TextChoices):
        FSW = 'FSW', _('Female Sex Workers')
        MSM = 'MSM', _('Men Who Have Sex With Men')
        PWID = 'PWID', _('People Who Inject Drugs')
        TG = 'TG', _('Transgender')
        INTERSEX = 'INTERSEX', _('Intersex')
        LBQ = 'LBQ', _('Lesbian Bisexual or Queer')
        OTHER = 'OTHER', _('Other Key Population Status')

    class DisabilityType(models.TextChoices):
        VI = 'VI', _('Visually Impaired')
        PD = 'PD', _('Physical Disability')
        ID = 'ID', _('Intellectual Disability')
        HI = 'HD', _('Hearing Impaired')
        PSY = 'PSY', _('Psychiatric Disability')
        SI = 'SI', _('Speech Impaired')
        OTHER = 'OTHER', _('Other Disability')

    class AgeRange(models.TextChoices):
        U18 = 'under_18', _('Under 18')
        ET_24 = '18_24', _('18–24')
        T5_34 = '25_34', _('25–34')
        T5_44 = '35_44', _('35–44')
        F5_64 = '45_64', _('45–64')
        O65 = '65_plus', _('65+')

    class Citizenship(models.TextChoices):
        CIT = 'citizen', _('Citizen')
        NC = 'non_citizen', _('Non-Citizen')

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    count = models.PositiveIntegerField()
    sex = models.CharField(max_length = 2, choices=Sex.choices, null=True, blank=True)
    age_range = models.CharField(max_length = 25, choices=AgeRange.choices, null=True, blank=True)
    citizenship = models.CharField(max_length = 25, choices=Citizenship.choices, null=True, blank=True)
    hiv_status = models.BooleanField(null=True, blank=True)
    pregnancy = models.BooleanField(null=True, blank=True)
    disability_type = models.CharField(max_length = 25, choices=DisabilityType.choices, null=True, blank=True)
    kp_type = models.CharField(max_length = 25, choices=KeyPopulationType.choices, null=True, blank=True)
    status = models.CharField(max_length = 25, choices=Status.choices, null=True, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, null=True, blank=True)
    subcategory = models.ForeignKey(IndicatorSubcategory, on_delete=models.PROTECT, null=True, blank=True)

    flagged = models.BooleanField(default=False)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='count_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='count_updated_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('event', 'sex', 'age_range', 'citizenship', 'task', 'subcategory',
                           'hiv_status', 'pregnancy', 'disability_type', 'kp_type', 'status', 'organization')
        indexes = [
            models.Index(fields=['event']),
            models.Index(fields=['task']),
        ]
    
    def __str__(self):
        return f"{self.count} @ {self.event.name} ({self.sex}, {self.age_range}, {self.organization})"