from django.db import models
from django.utils.translation import gettext_lazy as _

from users.models import User

class Indicator(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'Active', _('Active')
        DEPRECATED = 'Deprecated', _('Deprecated')
        PLANNED = 'Planned', _('Planned')
    name = models.CharField(max_length=255, verbose_name='Indicator Text')
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.ACTIVE, verbose_name='Indicator Status')
    code = models.CharField(max_length=10, verbose_name='Indicator Code')
    prerequisite = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Prerequisite Indicator')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'{self.code}: {self.name}'

class IndicatorSubcategory(models.Model):
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name='subcategories')
    code = models.CharField(max_length=10, verbose_name='Category Code', help_text='To help if you want to track between options in two indicators')
    name = models.CharField(max_length=255, verbose_name='Category Name')