from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
User = get_user_model()


class Assessment(models.Model):
    name = models.CharField(max_length = 255, verbose_name='Assessment Name')
    description = models.TextField(verbose_name='Description', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assessment_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assessment_updated_by')

    def __str__(self):
        return f'{self.name}'
    
class Indicator(models.Model):

    class Type(models.TextChoices):
        BOOL = 'boolean', _('Yes/No')
        SINGLE = 'single', _('Single Select')
        MULTI = 'multi', _('Mutliselect')
        TEXT = 'text', _('Open Answer')
        INT = 'integer', _('Number')

    class Category(models.TextChoices):
        ASS = 'assessment', _('Assessment-Based')
        SOCIAL = 'social', _('Social Media')
        EVENTS = 'events', _('Number of Events / Outreach')
        ORGS = 'orgs', _('Organizations Capacitated')
        MISC = 'misc', _('Other Category')

    name = models.CharField(max_length=255)
    required = models.BooleanField(default=False)
    type = models.CharField(max_length=25, choices=Type.choices, default=Type.BOOL, verbose_name='Data Type')
    category = models.CharField(max_length=25, choices=Category.choices, default=Category.ASS)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, null=True, blank=True)
    match_options = models.ForeignKey('self', blank=True, null=True, on_delete=models.SET_NULL)
    allow_none = models.BooleanField(default=False)
    allow_aggregate = models.BooleanField(default=False)
    order = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='de_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='de_updated_by')
    
    def __str__(self):
        return f'{self.name}'
    
class Option(models.Model):
    name = models.CharField(max_length=255)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    deprecated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='option_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='option_updated_by')

    def __str__(self):
        return f'{self.name}'

class LogicGroup(models.Model):
    class Operator(models.TextChoices):
        AND = 'AND', _('And')
        OR = 'OR', _('Or')

    indicator = models.ForeignKey(Indicator, related_name="logic_groups", on_delete=models.CASCADE)
    group_operator = models.CharField(max_length=3, choices=Operator.choices, default=Operator.AND)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='logic_group_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='logic_group_updated_by')

class LogicCondition(models.Model):
    group = models.ForeignKey(LogicGroup, related_name="conditions", on_delete=models.CASCADE)

    class SourceType(models.TextChoices):
        ASS = 'assessment', _('Indicator in This Assessment')
        RES = 'respondent', _('Respondent Field')
    class RespondentField(models.TextChoices):
        SEX = 'sex', _('Sex')
        HIV = 'hiv_status', _('HIV Status')
    class Operator(models.TextChoices):
        EQUALS = '=', _('Equals'),
        NE = '!=', _('Not Equals'),
        GT = '>', _('Greater Than'),
        LT = '<', _('Less Than'),
        C = 'contains', _('Contains'),
        DNC = '!contains', _('Does Not Contain'),
    
    class ExtraChoices(models.TextChoices):
        ANY= 'any', _('Any')
        ALL= 'all', _('All')
        NONE= 'none', _('None')

    RESPONDENT_VALUE_CHOICES = {
        'sex': [{'value': 'M', 'label': 'Male'}, {'value': 'F', 'label': 'Female'}, {'value': 'NB', 'label': 'Non Binary'}],
        'hiv_positive': [{'value': True, 'label': 'HIV Positive'}, {'value': False, 'label': 'HIV Negative'}],
    }

    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.ASS)
    source_indicator = models.ForeignKey(
        Indicator, null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text="Used if source_type = indicator"
    )
    respondent_field = models.CharField(
        max_length=100,
        null=True, blank=True,
        help_text="Used if source_type = respondent",
    )
    operator = models.CharField(max_length=10, choices=Operator.choices, default=Operator.EQUALS)
    value_text = models.CharField(max_length=255, null=True, blank=True)
    value_option = models.ForeignKey(
        'Option',
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    condition_type = models.CharField(max_length=10, choices=ExtraChoices.choices, default=ExtraChoices.ANY, null=True, blank=True)
    value_boolean = models.BooleanField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='condition_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='condition_updated_by')
    