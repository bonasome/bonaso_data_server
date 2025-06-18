from django.db import models
from organizations.models import Organization
from indicators.models import Indicator
from users.models import User
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

class Client(models.Model):
    name = models.CharField(max_length=255, verbose_name='Client Organization Name')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Project(models.Model):
    class Status(models.TextChoices):
        PLANNED = 'Planned', _('Planned')
        ACTIVE = 'Active', _('Active')
        COMPLETED = 'Completed', _('Completed')
        ON_HOLD = 'On_hold', _('On Hold')

    name = models.CharField(max_length=255, verbose_name='Project Name')
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.PLANNED, verbose_name='Project Status')
    client = models.ForeignKey(Client, verbose_name='Project Organized on Behalf of', blank=True, null=True, default=None, on_delete=models.SET_DEFAULT)
    organizations = models.ManyToManyField(Organization, through='ProjectOrganization', blank=True)
    indicators = models.ManyToManyField(Indicator, through='ProjectIndicator', blank=True)
    start = models.DateField(verbose_name='Project Start Date')
    end = models.DateField(verbose_name='Project Completion Date')
    description = models.TextField(blank=True, null=True, verbose_name='Project Description')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Project {self.name} for {self.client}'

class ProjectOrganization(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)

class ProjectIndicator(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True)

class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_DEFAULT, default=None, null=True, blank=True)
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
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
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

