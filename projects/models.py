from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

from organizations.models import Organization
from indicators.models import Indicator, Assessment
from django.contrib.auth import get_user_model
User = get_user_model()

class Client(models.Model):
    '''
    Model for tracking who a project is for. Mostly useful for segmenting what client users are allowed
    to view.

    We could have used organizations for this, but that might have complicated the org model too much, so better
    to segment the logic to another model.
    '''
    name = models.CharField(max_length=255, verbose_name='Client Organization Name')
    full_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='Client Organization Full Name')
    description = models.TextField(blank=True, null=True, verbose_name='Client Description')

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='client_created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='client_updated_by')

    def __str__(self):
        return self.name

class Project(models.Model):
    '''
    The project is kind of the organizing nexus where a lot of things intersect. Projects have organizaitons
    and organizations are assigned indicators via a task. Project dates are used for validation and its also
    the unit that houses tasks and targets. 

    Also linked a few things like activities and deadlines that help with organizing projects.

    FIELDS:
        -Status: Mostly for admin tracking, but non-admins only see active projects
        -Organizaitons: Used to track which organizations should be able to view information related to this
            project.
        
    '''
    class Status(models.TextChoices):
        PLANNED = 'Planned', _('Planned')
        ACTIVE = 'Active', _('Active')
        COMPLETED = 'Completed', _('Completed')
        ON_HOLD = 'on_hold', _('On Hold')

    name = models.CharField(max_length=255, verbose_name='Project Name')
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PLANNED, verbose_name='Project Status')
    client = models.ForeignKey(Client, verbose_name='Project Organized on Behalf of', blank=True, null=True, default=None, on_delete=models.SET_DEFAULT)
    organizations = models.ManyToManyField(Organization, through='ProjectOrganization', blank=True, through_fields=('project', 'organization'),)
    start = models.DateField(verbose_name='Project Start Date')
    end = models.DateField(verbose_name='Project Completion Date')
    description = models.TextField(blank=True, null=True, verbose_name='Project Description')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='project_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='project_updated_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name}'

class ProjectOrganization(models.Model):
    '''
    This is a through table for organizations, but also stores if a organization is a child or another org.
    This helps with mapping project hirearchies, but also helps manage permissions for things related to projects
    Like, parent orgs should be able to edit content for their child orgs (events, interactions, etc.).
    '''
    parent_organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, blank=True, null=True, related_name='child_links') #this organizations parent. Only one layer of parent --> child is supported
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='org_links')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='project_organization')
    
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)


class Task(models.Model):
    '''
    The task is a link between a project, organization, and an indicator. It is linked to events/interactions
    and is the chief way that we track who is doing what. 

    Tasks can't really be updated since they are just a nexus. They are either created or destroyed.
    '''
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, null=True, blank=True)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='task_created_by')
    
    class Meta:
        unique_together = ('project', 'organization', 'indicator', 'assessment')

    def __str__(self):
        if self.assessment:
            return f'{self.assessment} ({self.organization}, {self.project})'
        if self.indicator:
            return f'{self.indicator} ({self.organization}, {self.project})'
    
class Target(models.Model):
    '''
    A target is a mark of acheivement linked to a task. It can either be measured as a raw amount (15, 34, 10005)
    or as a percentage of a related task (i.e., 100% of people tested positive for HIV referred for ART).
    This related to method requires both a task object and a numeric percentage (0-100)

    Targets have start and end periods, and targets with the same linked task cannot overlap.
    '''
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    amount = models.IntegerField(verbose_name= 'Target Amount', blank=True, null=True)
    start = models.DateField('Target Start Date')
    end = models.DateField('Target Conclusion Date')
    related_to = models.ForeignKey(Task, related_name='related_to_task', on_delete=models.CASCADE, blank=True, null=True) #task to use for target amount
    percentage_of_related = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], null=True, blank=True) #percentage of that task to achieve

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='target_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='target_updated_by')
    

    def clean(self):
        '''
        Make sure that either an amount or related to pair is there. Also check no overlaps or weird date things.
        '''
        super().clean()
        if not self.amount:
            if not self.related_to or self.percentage_of_related is None:
                raise ValidationError("A target must have either an amount or a related task and percentage.")
        if self.amount:
            if self.related_to or self.percentage_of_related:
                raise ValidationError('Plese set this target either as an amount or as a percentage.')
        if self.start > self.end:
            raise ValidationError('Start date must be before end date')
        overlaps = Target.objects.filter(
            task=self.task,
            start__lte=self.end,
            end__gte=self.start
        )
        if self.pk:
            overlaps = overlaps.exclude(pk=self.pk)

        if overlaps.exists():
            raise ValidationError("Target date range overlaps with an existing target.")

    def __str__(self):
        return f'Target for {self.indicator} ({self.start} - {self.end})'
class ProjectActivity(models.Model):
    '''
    An organizational tool that can help admins/orgs track when events are and such. No real bearing on the data,
    purely organizational.

    Visible to all makes this public to any org in the project, while specifying an org will limit it to the 
    organizations listed (and their children if cascade_to_children is true.)
    '''

    class Category(models.TextChoices):
        GEN = 'general', _('General Activity') #misc
        ME = 'me', _('Monitoring and Evaluation') #m&e, data checkins
        FINANCE = 'finance', _('Finance') #finance
        TRAINING = 'training', _('Training') #training/capacity building
        MILESTONE = 'milestone', _('Milestone') #mid term, project launch, closeout, etc

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organizations = models.ManyToManyField(Organization, through='ProjectActivityOrganization')
    visible_to_all = models.BooleanField(default=False) #display to all project members
    cascade_to_children = models.BooleanField(default=False) #if assigned to one org, also cascade to to child orgs automatically
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    start = models.DateField()
    end = models.DateField()
    status = models.CharField(max_length=25, choices=Project.Status.choices, default=Project.Status.PLANNED)
    category = models.CharField(max_length=25, choices=Category.choices, default=Category.GEN)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='activity_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='activity_updated_by')

    def __str__(self):
        return f'{self.name} ({self.project})'

class ProjectActivityOrganization(models.Model):
    '''
    Through table for above organizaitons field
    '''
    project_activity = models.ForeignKey(ProjectActivity, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

class ProjectActivityComment(models.Model):
    '''
    This isn't fully implemented, but the idea is to allow for comments on activities eventually.
    '''
    activity = models.ForeignKey(ProjectActivity, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    content = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']


class ProjectDeadline(models.Model):
    '''
    Deadlines are similar to activities in that they are mostly organizational, but they are tied into the 
    alerts system. 
    '''
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organizations = models.ManyToManyField(Organization, through='ProjectDeadlineOrganization')
    visible_to_all = models.BooleanField(default=False) #make visible to all project members
    cascade_to_children = models.BooleanField(default=False) #if assigned to one org, auto cascade it to child orgs
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    deadline_date = models.DateField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='deadline_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='deadline_updated_by')
    
    def __str__(self):
        return f'{self.name} ({self.project})'
class ProjectDeadlineOrganization(models.Model):
    '''
    Largely a through table, but also stores information about the specific org (maybe push the deadline back)
    or whether its completed.
    '''
    deadline = models.ForeignKey(ProjectDeadline, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    organization_deadline = models.DateField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True) #track if maybe the deadline or complete status was updated
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='deadline_organization_updated_by')

    class Meta:
        unique_together = ('deadline', 'organization')