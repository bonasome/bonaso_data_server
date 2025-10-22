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
    '''
    An indicator is a thing that data is tracked about. They can either be standalone (category Social,
    events, orgs, misc) or part of an assessment. If part of an assessment, they can be associated with a 
    specific type, indicating what data they collect, logic, and fields like required/match_options to manage
    assessment flows.

    Indicators can be set to allow aggregates. 
    '''
    class Type(models.TextChoices):
        BOOL = 'boolean', _('Yes/No') #boolean value
        SINGLE = 'single', _('Single Select') #single option
        MULTI = 'multi', _('Mutliselect') #multiple options
        TEXT = 'text', _('Open Answer') #text response
        INT = 'integer', _('Number') #integer
        MULTINT = 'multint', _('Numbers by Category') #multiple options with a number attached
        
    class Category(models.TextChoices):
        ASS = 'assessment', _('Assessment-Based') #linked to an assessment
        SOCIAL = 'social', _('Social Media') #linked to a social media post, and uses metrics built into that model
        EVENTS = 'events', _('Number of Events / Outreach') #linked to an event, and pulls number of events linked to
        ORGS = 'orgs', _('Organizations Capacitated') #linked to event, and pulls participating orgs
        MISC = 'misc', _('Other Category') #generic misc that can be attached to a count

    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True) 
    required = models.BooleanField(default=False) #for assessment, is this required
    type = models.CharField(max_length=25, choices=Type.choices, default=Type.BOOL, verbose_name='Data Type') # if assessment, what type of data is being collected
    category = models.CharField(max_length=25, choices=Category.choices, default=Category.ASS) #template for the indicator
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, null=True, blank=True)
    match_options = models.ForeignKey('self', blank=True, null=True, on_delete=models.SET_NULL) #for multiselect, the options will be limited based on a previous indicator in the assessment
    allow_none = models.BooleanField(default=False) #add a none option (not stored as a response, but for managing logic/requirements)
    allow_aggregate = models.BooleanField(default=False) #allow this indicator to be linked to an aggregate count
    order = models.PositiveIntegerField(null=True, blank=True) #order this will appear in an assessment

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='de_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='de_updated_by')
    
    def __str__(self):
        return f'{self.name}'
    
class Option(models.Model):
    '''
    Option linked to a single select, multiselect, or multint type indicator. Allows a user to select/
    enter information from a list of predefined options.
    '''
    name = models.CharField(max_length=255)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    deprecated = models.BooleanField(default=False) #don't delete options, since they may be linked to responses. Instead deprecate them.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='option_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='option_updated_by')

    def __str__(self):
        return f'{self.name}'

class LogicGroup(models.Model):
    '''
    Group of logic in a one-to-one relationship with an indicator in an assessment. Determines the operator
    (all or one must be true).
    '''
    class Operator(models.TextChoices):
        AND = 'AND', _('All Conditions')
        OR = 'OR', _('Any Condition')

    indicator = models.ForeignKey(Indicator, related_name="logic_groups", on_delete=models.CASCADE)
    group_operator = models.CharField(max_length=3, choices=Operator.choices, default=Operator.AND)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='logic_group_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='logic_group_updated_by')

class LogicCondition(models.Model):
    '''
    Logical condition that determines if a question should be displayed or not. Can be based on the response
    to an indicator in the same assessment or based on a respondent field. 
    '''
    group = models.ForeignKey(LogicGroup, related_name="conditions", on_delete=models.CASCADE)

    class SourceType(models.TextChoices):
        ASS = 'assessment', _('Indicator in This Assessment')
        RES = 'respondent', _('Respondent Field')
        
    class RespondentField(models.TextChoices):
        SEX = 'sex', _('Sex')
        HIV = 'hiv_status', _('HIV Status')

    class Operator(models.TextChoices):
        EQUALS = '=', _('Is Equal To'),
        NE = '!=', _('Does Not Equal'),
        # for number only
        GT = '>', _('Is Greater Than'),
        LT = '<', _('Is Less Than'),
        #for text only
        C = 'contains', _('Contains'),
        DNC = '!contains', _('Does Not Contain'),
    
    class ExtraChoices(models.TextChoices):
        ANY= 'any', _('Any') #any option selected
        ALL= 'all', _('All') #all options selected
        NONE= 'none', _('None') #none option selected if indicator allows none

    #helper map that validates what options are valid for value_text if the source is a respondent
    RESPONDENT_VALUE_CHOICES = {
        'sex': [{'value': 'M', 'label': 'Male'}, {'value': 'F', 'label': 'Female'}, {'value': 'NB', 'label': 'Non Binary'}],
        'hiv_status': [{'value': "true", 'label': 'HIV Positive'}, {'value': "false", 'label': 'HIV Negative'}],
    }

    source_type = models.CharField(max_length=20, choices=SourceType.choices, default=SourceType.ASS) #assessment or respondent
    source_indicator = models.ForeignKey(
        Indicator, null=True, blank=True,
        on_delete=models.SET_NULL,
        help_text="Used if source_type = indicator"
    ) #indicator that must be answered
    respondent_field = models.CharField(
        max_length=100,
        null=True, blank=True,
        help_text="Used if source_type = respondent",
    ) #respondent field that must be true
    operator = models.CharField(max_length=10, choices=Operator.choices, default=Operator.EQUALS) #equals, contains, etc.
    value_text = models.CharField(max_length=255, null=True, blank=True) #textual (or numeric) value to compare to
    value_option = models.ForeignKey(
        'Option',
        null=True, blank=True,
        on_delete=models.SET_NULL
    ) #fk to option to compare to
    condition_type = models.CharField(max_length=10, choices=ExtraChoices.choices, null=True, blank=True) #for option types, check if any, all, or none are selected
    value_boolean = models.BooleanField(null=True, blank=True) #boolean to compare to

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='condition_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='condition_updated_by')
    