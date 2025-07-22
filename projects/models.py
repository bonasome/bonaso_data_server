from django.db import models
from organizations.models import Organization
from indicators.models import Indicator
from users.models import User
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

class Client(models.Model):
    name = models.CharField(max_length=255, verbose_name='Client Organization Name')
    full_name = models.CharField(max_length=255, blank=True, null=True, verbose_name='Client Organization Full Name')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='client_created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='client_updated_by')
class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'Planned', _('Planned')
        ACTIVE = 'Active', _('Active')
        COMPLETED = 'Completed', _('Completed')
        ON_HOLD = 'On_hold', _('On Hold')

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
        return f'Project {self.name} for {self.client}'

class ProjectOrganization(models.Model):
    parent_organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, blank=True, null=True, related_name='child_links')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='org_links')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='project_organization')
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)


class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='task_created_by')
    class Meta:
        unique_together = ('project', 'organization', 'indicator')

    def __str__(self):
        return f'{self.organization}, {self.indicator} ({self.project})'
    
class Target(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    amount = models.IntegerField(verbose_name= 'Target Amount', blank=True, null=True)
    start = models.DateField('Target Start Date')
    end = models.DateField('Target Conclusion Date')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='target_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='target_updated_by')
    related_to = models.ForeignKey(Task, related_name='related_to_task', on_delete=models.CASCADE, blank=True, null=True)
    percentage_of_related = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(100)], null=True, blank=True)

    
    def clean(self):
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

class ProjectActivity(models.Model):
    class Category(models.TextChoices):
        GEN = 'general', _('General Activity') #misc
        ME = 'me', _('Monitoring and Evaluation') #m&e, data checkins
        FINANCE = 'finance', _('Finance') #finance
        TRAINING = 'training', _('Training') #training/capacity building
        MILESTONE = 'milestone', _('Milestone') #mid term, project launch, closeout, etc

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organizations = models.ManyToManyField(Organization, through='ProjectActivityOrganization')
    visible_to_all = models.BooleanField(default=False)
    cascade_to_children = models.BooleanField(default=False)
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


class ProjectActivityOrganization(models.Model):
    project_activity = models.ForeignKey(ProjectActivity, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

class ProjectActivityComment(models.Model):
    activity = models.ForeignKey(ProjectActivity, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    content = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']