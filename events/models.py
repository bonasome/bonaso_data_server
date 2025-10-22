from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from organizations.models import Organization
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

    Events can be tied to any Indicator via a task, and can be used to track indicators that track number of events or organizations capacitated. 

    KEY FIELDS:
        Event Type: Mainly used for categorization/filtering
        Status: Useful tracking tool, but also only completed events contribute towards targets for event_no/event_org_no type indicators
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
    organizations = models.ManyToManyField(Organization, through='EventOrganization', blank=True) # list of participating organizations, used to calc org_event_numbers and can be used to add tasks for other orgs
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
    Through model for participating orgs.
    '''
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)

class EventTask(models.Model):
    '''
    Through model for related tasks.
    '''
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)