from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _

class User(AbstractUser):
    '''
    Custom user model: Has custom fields for organization (required, used in many checks), role (
    used for many checks, required), and client organization (keep client and participant logic seperate).
    '''
    class Role(models.TextChoices):
        '''
        Be very careful when editing role value strings, as these are hard coded throughout the server and the frontend
        '''
        VIEW_ONLY = 'view_only', _('View Only') #has no privleges, used to await admin approval
        DATA_COLLECTOR = 'data_collector', _('Data Collector') #has limited privlleges to create respondent level information
        SUPERVISOR = 'supervisor', _('Supervisor') #currently not in use
        MEOFFICER = 'meofficer', _('Monitoring and Evaluation Officer') #has advanced proveleges to manage content related to their org and their child orgs (--> see projects model)
        MANAGER = 'manager', _('Manager') #same as M&E
        ADMIN = 'admin', _('Site Administrator') #can basically do everything
        CLIENT = 'client', _('Client') #can view almost everything related to their project, but no create/patch abilities

    phone_number = models.CharField(max_length=15, blank=True, null=True, help_text='e.g. +267 71 234 567')
    organization = models.ForeignKey('organizations.Organization', on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=25, choices=Role.choices, default=Role.VIEW_ONLY, help_text='Set user access level and permission. Leave as "Data Collector" if unsure.')
    client_organization = models.ForeignKey('projects.Client', on_delete=models.SET_NULL, null=True, blank=True)
    
    def __str__(self):
        return f'{self.first_name} {self.last_name}'


