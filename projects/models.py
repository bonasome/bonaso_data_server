from django.db import models
from organizations.models import Organization
from indicators.models import Indicator
from users.models import User
from django.utils.translation import gettext_lazy as _

class Client(models.Model):
    name = models.CharField(max_length=255, verbose_name='Client Organization Name')
    created_by = models.ForeignKey(User, on_delete=models.SET_DEFAULT, default=None, null=True, blank=True)
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
    organization = models.ManyToManyField(Organization, through='ProjectOrganization', blank=True, null=True)
    indicators = models.ManyToManyField(Indicator, through='ProjectIndicator', blank=True, null=True)
    start = models.DateField(verbose_name='Project Start Date')
    end = models.DateField(verbose_name='Project Completion Date')
    description = models.TextField(blank=True, null=True, verbose_name='Project Description')
    created_by = models.ForeignKey(User, on_delete=models.SET_DEFAULT, default=None, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Project {self.name} for {self.client}'

class ProjectOrganization(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

class ProjectIndicator(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)

class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)