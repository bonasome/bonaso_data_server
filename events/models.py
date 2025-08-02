from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from organizations.models import Organization
from indicators.models import IndicatorSubcategory
from projects.models import Task
from django.contrib.contenttypes.fields import GenericRelation

User = get_user_model()

class Event(models.Model):
    '''
    The event model is meant to track be a container to track information around specific activities
    that occured surrounding a project. This could include trainings, commemorations, activations, or anything.

    Events are primairly designed to track things like staff trainings, where storing respondent infomation 
    may not be necessary. It can also be used to track certian indicators like (how many counselling sessions
    were conducted in a month). 

    Events can be tied to any Indicator via a task and information is recorded via counts (see below). 

    KEY FIELDS:
        Event Type: Mainly used for categorization/filtering
        Status: Useful tracking tool, but also only completed events contribute towards targets
        Host: The hosting organization, will default to the users if not an admin, can be left blank by admins (
        for creating public/multi-org events).
        Organizations: The organizations that participated in this event. Governs which tasks are available.
        Tasks: The tasks (or indicators) that this event contributes towards. Depending on the indicator type,
        these may depend on counts or they may be auto-calced.

    '''
    class EventStatus(models.TextChoices):
        PLANNED = 'planned', _('Planned') 
        COMPLETED = 'completed', _('Completed')
        IN_PROGRESS = 'in_progress', _('In Progress')
        ON_HOLD = 'on_hold', _('On Hold')

    class EventType(models.TextChoices):
        TRAINING = 'training', _('Training') 
        ACTIVITY = 'activity', _('Activity')
        ENGAGEMENT = 'engagement', _('Engagement')
        COMM = 'commemoration', _('Commemoration')
        ACTIVATION = 'activation', _('Activation')
        WALK = 'walkathon', _('Walkathon')
        COU = 'counselling_session', _('Counselling Session')
        OTH = 'other', _('Other')
        
    name = models.CharField(max_length=255, verbose_name='Event Name')
    description = models.TextField(verbose_name='Description of Event', blank=True, null=True)
    event_type = models.CharField(max_length=25, choices=EventType.choices, default=EventType.TRAINING, verbose_name='Event Type')
    status = models.CharField(max_length=25, choices=EventStatus.choices, default=EventStatus.PLANNED, verbose_name='Event Status')
    host = models.ForeignKey(Organization, verbose_name='Hosting Organization', on_delete=models.SET_NULL, blank=True, null=True, related_name='host')
    organizations = models.ManyToManyField(Organization, through='EventOrganization', blank=True)
    tasks = models.ManyToManyField(Task, through='EventTask', blank=True)
    location = models.CharField(max_length=255, verbose_name='Event Location')
    start = models.DateField()
    end = models.DateField()
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='event_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='event_updated_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
class EventOrganization(models.Model):
    '''
    Through model for orgs.
    '''
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)

class EventTask(models.Model):
    '''
    Through model for tasks.
    '''
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)

class DemographicCount(models.Model):
    '''
    The demographic count is how numeric information (how many people) is attached to an event. For example,
    how many people tested, how many staff trained, etc. We allow dynamic splitting by the following demographic
    categories. Each count is linked to one event.

    These categories should match with their corresponding ones from the respondents model.

    Each count must be linked to a task (this is how the system knows what to do with it.)
    We also have a business logic rule that one task can only have one set of counts (visualize it like a table).
    There's a nascent idea to allow organizations breakdowns (for training maybe) but right now that field is dormant.
    '''
    class Sex(models.TextChoices):
        FEMALE = 'F', _('Female')
        MALE = 'M', _('Male')
        NON_BINARY = 'NB', _('Non-Binary')

    class Status(models.TextChoices):
        STAFF = 'staff', _('Staff')
        COMMUNITY_LEADER = 'community_leader', _('Community Leader')
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
        F4_59 = '55_55', _('55-59')
        S0_64 = '60_64', _('60-64')
        O65 = '65_plus', _('65+')

    class Citizenship(models.TextChoices):
        CIT = 'citizen', _('Citizen')
        NC = 'non_citizen', _('Non-Citizen')
    
    class Pregnancy(models.TextChoices):
        YES = 'pregnant', _('Pregnant')
        NO = 'not_pregnant', _('Not Pregnant')
    
    class HIVStatus(models.TextChoices):
        YES = 'hiv_positive', _('HIV Positive')
        NO = 'hiv_negative', _('HIV Negative')

    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    count = models.PositiveIntegerField()
    sex = models.CharField(max_length = 2, choices=Sex.choices, null=True, blank=True)
    age_range = models.CharField(max_length = 25, choices=AgeRange.choices, null=True, blank=True)
    citizenship = models.CharField(max_length = 25, choices=Citizenship.choices, null=True, blank=True)
    hiv_status = models.CharField(max_length = 25, choices=HIVStatus.choices, null=True, blank=True)
    pregnancy = models.CharField(max_length = 25, choices=Pregnancy.choices, null=True, blank=True)
    disability_type = models.CharField(max_length = 25, choices=DisabilityType.choices, null=True, blank=True)
    kp_type = models.CharField(max_length = 25, choices=KeyPopulationType.choices, null=True, blank=True)
    status = models.CharField(max_length = 25, choices=Status.choices, null=True, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, null=True, blank=True)
    subcategory = models.ForeignKey(IndicatorSubcategory, on_delete=models.PROTECT, null=True, blank=True)
    flags = GenericRelation('flags.Flag', related_query_name='flags')

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
        return f"{self.count} @ {self.event.name} ({self.task.indicator.name}, {self.task.organization.name})"