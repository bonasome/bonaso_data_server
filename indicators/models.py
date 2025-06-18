from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from users.models import User

class IndicatorSubcategory(models.Model):
    name = models.CharField(max_length=255, verbose_name='Category Name')

    def __str__(self):
        return self.name

class Indicator(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'Active', _('Active')
        DEPRECATED = 'Deprecated', _('Deprecated')
        PLANNED = 'Planned', _('Planned')
    name = models.CharField(max_length=255, verbose_name='Indicator Text')
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.ACTIVE, verbose_name='Indicator Status')
    code = models.CharField(max_length=10, verbose_name='Indicator Code')
    prerequisite = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, verbose_name='Prerequisite Indicator')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    require_numeric = models.BooleanField(blank=True, null=True, default=False, verbose_name='Indicator requires an accompanying numeric value.')
    subcategories = models.ManyToManyField(IndicatorSubcategory, blank=True)

    def clean(self):
        if self.prerequisite_id == self.id:
            self.prerequisite = None
            #raise ValidationError("An indicator cannot be its own prerequisite.")
    
    def __str__(self):
        return f'{self.code}: {self.name}'
