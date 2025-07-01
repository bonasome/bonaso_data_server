from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    class Role(models.TextChoices):
        VIEW_ONLY = 'view_only', _('View Only')
        DATA_COLLECTOR = 'data_collector', _('Data Collector')
        SUPERVISOR = 'supervisor', _('Supervisor')
        MEOFFICER = 'meofficer', _('Monitoring and Evaluation Officer')
        MANAGER = 'manager', _('Manager')
        ADMIN = 'admin', _('Site Administrator')
        CLIENT = 'client', _('Client')

    phone_number = models.CharField(max_length=15, blank=True, null=True, help_text='e.g. +267 71 234 567')
    organization = models.ForeignKey('organizations.Organization', on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=25, choices=Role.choices, default=Role.VIEW_ONLY, help_text='Set user access level and permission. Leave as "Data Collector" if unsure.')
    client_organization = models.ForeignKey('projects.Client', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f'{self.first_name} {self.last_name}'


