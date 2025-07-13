from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from users.models import User

class IndicatorSubcategory(models.Model):
    name = models.CharField(max_length=255, verbose_name='Category Name')
    slug = models.CharField(max_length=255, blank=True)

    def save(self, *args, **kwargs):
        self.slug = ''.join(self.name.lower().split())  # lowercase + no spaces
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.name

class Indicator(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'Active', _('Active')
        DEPRECATED = 'Deprecated', _('Deprecated')
        PLANNED = 'Planned', _('Planned')
    class IndicatorType(models.TextChoices):
        RESPONDENT = 'Respondent', _('Respondent') #this indicator relies on a respondent, and will appear on respondent
        COUNT = 'Count', _('Count') #this indicator will not appear on respondent pages, but will be available via events

    name = models.CharField(max_length=255, verbose_name='Indicator Text')
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.ACTIVE, verbose_name='Indicator Status')
    indicator_type = models.CharField(max_length=25, choices=IndicatorType.choices, default=IndicatorType.RESPONDENT, verbose_name='Indicator Type')
    code = models.CharField(max_length=10, verbose_name='Indicator Code')
    prerequisite = models.ForeignKey('self', on_delete=models.SET_NULL, blank=True, null=True, verbose_name='Prerequisite Indicator')
    required_attribute = models.ManyToManyField('respondents.RespondentAttributeType', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='indicator_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='indicator_updated_by')
    require_numeric = models.BooleanField(blank=True, null=True, default=False, verbose_name='Indicator requires an accompanying numeric value.')
    subcategories = models.ManyToManyField(IndicatorSubcategory, blank=True)
    allow_repeat = models.BooleanField(default=False, blank=True, null=True)
    '''
    def clean(self):
        if self.prerequisite_id == self.id:
            self.prerequisite = None
            raise ValidationError("An indicator cannot be its own prerequisite.")
        if self.prerequisite and self.prerequisite.indicator_type != self.indicator_type:
            raise ValidationError("Indicator prerequisite must be of the same type.")
    '''
    def __str__(self):
        return f'{self.code}: {self.name}'

