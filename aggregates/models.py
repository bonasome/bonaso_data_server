from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from organizations.models import Organization
from projects.models import Task, Project
from indicators.models import Indicator, Option
from respondents.models import Respondent, KeyPopulation, DisabilityType, RespondentAttributeType
from django.contrib.contenttypes.fields import GenericRelation
User = get_user_model()


class AggregateGroup(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    indicator = models.ForeignKey(Indicator, on_delete=models.PROTECT)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT)
    project = models.ForeignKey(Project, on_delete=models.PROTECT)
    start = models.DateField()
    end = models.DateField()
    comments = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='group_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='group_updated_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name if self.name else f"Aggregate for {self.indicator.name} ({self.start}-{self.end})"
class AggregateCount(models.Model):
    '''
    The demographic count is how numeric information (how many people) is attached to an event. For example,
    how many people tested, how many staff trained, etc. We allow dynamic splitting by the following demographic
    categories. Each count is linked to one event.

    These categories should match with their corresponding ones from the respondents model.

    Each count must be linked to a task (this is how the system knows what to do with it.)
    We also have a business logic rule that one task can only have one set of counts (visualize it like a table).
    There's a nascent idea to allow organizations breakdowns (for training maybe) but right now that field is dormant.
    '''
    
    #keep these three here
    class Citizenship(models.TextChoices):
        CIT = 'citizen', _('Citizen')
        NC = 'non_citizen', _('Non-Citizen')
    
    class Pregnancy(models.TextChoices):
        YES = 'pregnant', _('Pregnant')
        NO = 'not_pregnant', _('Not Pregnant')
    
    class HIVStatus(models.TextChoices):
        YES = 'hiv_positive', _('HIV Positive')
        NO = 'hiv_negative', _('HIV Negative')

    DEMOGRAPHIC_VALIDATORS = {
        'sex': Respondent.Sex.values,
        'age_range': Respondent.AgeRanges.values,
        'disability_type': DisabilityType.DisabilityTypes.values,
        'kp_type': KeyPopulation.KeyPopulations.values,
        'attribute_type': RespondentAttributeType.Attributes.values, 
        'citizenship': Citizenship.values,
        'hiv_status': HIVStatus.values,
        'pregnancy': Pregnancy.values,
        'districts': Respondent.District.values,

    }
    group = models.ForeignKey(AggregateGroup, on_delete=models.CASCADE)
    value = models.PositiveIntegerField() #numeric value
    sex = models.CharField(max_length = 2, choices=Respondent.Sex.choices, null=True, blank=True)
    age_range = models.CharField(max_length = 25, choices=Respondent.AgeRanges.choices, null=True, blank=True)
    district = models.CharField(max_length=50, choices=Respondent.District.choices, null=True, blank=True)
    citizenship = models.CharField(max_length = 25, choices=Citizenship.choices, null=True, blank=True)
    hiv_status = models.CharField(max_length = 25, choices=HIVStatus.choices, null=True, blank=True)
    pregnancy = models.CharField(max_length = 25, choices=Pregnancy.choices, null=True, blank=True)
    disability_type = models.CharField(max_length = 25, choices= DisabilityType.DisabilityTypes.choices, null=True, blank=True)
    kp_type = models.CharField(max_length = 25, choices=KeyPopulation.KeyPopulations.choices, null=True, blank=True)
    attribute_type = models.CharField(max_length = 25, choices=RespondentAttributeType.Attributes.choices, null=True, blank=True)
    option= models.ForeignKey(Option, on_delete=models.PROTECT, null=True, blank=True)
    unique_only = models.BooleanField(default=False)
    flags = GenericRelation('flags.Flag', related_query_name='flags')
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='count_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, default=None, null=True, blank=True, related_name='count_updated_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('group', 'sex', 'age_range', 'citizenship',
                           'hiv_status', 'pregnancy', 'disability_type', 'kp_type', 'attribute_type', 'option')
    
    def __str__(self):
        return f"Count for {self.group.indicator}"
