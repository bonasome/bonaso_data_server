from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
User = get_user_model()

def get_attribute_choices():
    from respondents.models import RespondentAttributeType
    return RespondentAttributeType.Attributes.choices

class IndicatorSubcategory(models.Model):
    '''
    A model that allows for indicators to have the eponymous subcategories that allow for more information
    to be attached to interactions. 
    
    Can be deprecated as needed and are no longer available to be 
    attached to new interactions (but old ones are preserved).
    '''
    name = models.CharField(max_length=255, verbose_name='Category Name')
    slug = models.CharField(max_length=255, blank=True)
    deprecated = models.BooleanField(null=True, default=False, blank=True)
    
    def save(self, *args, **kwargs):
        self.slug = ''.join(self.name.lower().split())  # lowercase + no spaces
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.name

class Indicator(models.Model):
    '''
    The indicator model is the key model that tracks the information we need to track. Any data that is 
    collected is tied to an indicator in some way. 

    FIELDS:
        -Status: helper field for admins to map things out. Only active indicators are viewable by others
        -Type: The type is basically how the indicator will be used, and determines what models it can be linked to
            --> Respondent? Interaction model (or counts)
            --> Social ? the Social model/
        -Prerequisite: Does this indicator rely on one or more other indicators (i.e. --> Screened for NCD --> Referred for NCD)
            - If so, it can be marked as a prerequisite to automatically flag suspect data.
        Requires Attribute: Things like HIV Positive of is a Community leader (for respondent types)
        Governs Attribute: Example, indicator test positive for HIV --> change respondent model to be HIV positive if not already
        Require Numeric: If this indicator is attached to an interaction, should it require a number (
            i.e., number of condoms given to a person)
        Sucategories: Many to many for the above model
        Match Subcategories: Will automatically this models subcategories to match with a prerequisite
        Allow Repeatr: By default any interaction that happen with the same person more than once within a 30
            day span is flagged. But this can be waived with setting this to true.

    '''
    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        DEPRECATED = 'deprecated', _('Deprecated')
        PLANNED = 'planned', _('Planned')

    class IndicatorType(models.TextChoices):
        '''
        WARNING: The frontend will try to reference these values as strings, so be careful when changing these, and if you
        do change these fields, reflect those changes in the frontend.
        '''
        RESPONDENT = 'respondent', _('Respondent') #this indicator relies on a respondent, and will appear on respondent
        SOCIAL = 'social', _('Social Media Post') #this indicator is linked to a seperate post model
        EVENT_NO = 'event_no', _('Number of Events') #by default, when this indicator is added to an event via a task, it will contribute to its count
        ORG_EVENT_NO = 'org_event_no', _('Number of Organizations at Event') #by default, when this indicator is added to an event via a task, it will use the number of organizations added (exlcuding the host) as its count

    name = models.CharField(max_length=255, verbose_name='Indicator Text')
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=25, choices=Status.choices, default=Status.ACTIVE, verbose_name='Indicator Status')
    indicator_type = models.CharField(max_length=25, choices=IndicatorType.choices, default=IndicatorType.RESPONDENT, verbose_name='Indicator Type')
    code = models.CharField(max_length=10, verbose_name='Indicator Code')
    prerequisites = models.ManyToManyField('self', blank=True, symmetrical=False, related_name='dependent_indicators', verbose_name='Prerequisite Indicators')
    required_attributes = models.ManyToManyField('respondents.RespondentAttributeType', blank=True)
    governs_attribute = models.CharField(max_length=25, choices=get_attribute_choices, blank=True, null=True)
    require_numeric = models.BooleanField(blank=True, null=True, default=False, verbose_name='Indicator requires an accompanying numeric value.')
    subcategories = models.ManyToManyField(IndicatorSubcategory, blank=True)
    match_subcategories_to = models.ForeignKey("self", on_delete=models.SET_NULL, blank=True, null=True)
    allow_repeat = models.BooleanField(default=False, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='indicator_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='indicator_updated_by')
    

    def __str__(self):
        return f'{self.code}: {self.name}'

