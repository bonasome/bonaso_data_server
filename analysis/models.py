from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from indicators.models import Assessment, Indicator
from projects.models import Project
from organizations.models import Organization
User = get_user_model()
class ChartField(models.Model):
    '''
    Shared enum storing model that handles controlled filter/legend/stack fields. If adding any fields to 
    the respondent/demogrpahic count model, make sure to reflect those changes here as well as [./utils/interactions_prep.py]
    (see the respondent/aggregate models for more).
    '''
    class Field(models.TextChoices):
        AR = 'age_range', _('Age Range')
        SEX = 'sex', _('Sex')
        KP ='kp_type', _('Key Population Type')
        DIS = 'disability_type', _('Disability Type')
        ATTR = 'special_attribute', _('Special Respondent Attribute')
        DIST = 'district', _('District')
        CIT = 'citizenship', _('Citizenship')
        HIV = 'hiv_status', _('HIV Status')
        PREG = 'pregnancy', ('Pregnancy')
        ORG = 'organization', ('Organization')
        OP = 'option', ('Option')
        P = 'platform', ('Platform')
        MET = 'metric', ('Metric')
    name = models.CharField(max_length=25, choices=Field.choices, unique=True)
    
class IndicatorChartSetting(models.Model):
    '''
    Chart settings: basically a storage system for users so that they can create charts and view them repeatedly.

    The current supported chart types are Pie, Line, and Bar:
        -Bar supports an axis (time period), legend (field), and stack (second field), unless multiple indicators are present
        -Line supports an axis and legend
        -Pie supports a legend
    All charts can also be filtered by the fields above (except organization, which is managed at the dashboard level and metric). 
    All charts can also include a data table.
    '''
    class ChartType(models.TextChoices):
        PIE = 'pie', _('Pie Chart')
        LINE = 'line', _('Line Chart')
        BAR = 'bar', _('Bar Chart')
    class AxisOptions(models.TextChoices):
        MONTH  = 'month', _('Month')
        QUARTER = 'quarter', _('Quarter')
    
    name = models.CharField(max_length=255, blank=True, null=True)
    indicators = models.ManyToManyField(Indicator, through='ChartIndicator') # indicators to chart. More than one indicator and the indicator will be treated as the legend
    chart_type = models.CharField(max_length=25, choices=ChartType.choices, default=ChartType.BAR, null=True, blank=True)
    tabular = models.BooleanField(default=False) #also show a data table
    axis = models.CharField(max_length=25, choices=AxisOptions.choices, default=AxisOptions.QUARTER, null=True, blank=True) # time period to display on x axis (corresponds to split)
    legend = models.CharField(max_length=25, choices=ChartField.Field.choices, default=None, null=True, blank=True) # legend (corresponds to params)
    stack = models.CharField(max_length=25, choices=ChartField.Field.choices, default=None, null=True, blank=True) #for bar charts (second param)
    use_target = models.BooleanField(default=False) #determines whether or not to show targets (will disable legend/stack)
    filters = models.ManyToManyField(ChartField, through='ChartFilter', blank=True, related_name='chart_filters') #chart field filters
    average = models.BooleanField(default=False)
    #for mapping repeated only
    repeat_only = models.BooleanField(default=False)
    repeat_n = models.PositiveIntegerField(null=True, blank=True)

    #seperate date filters not linked to fields
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='chart_settings_created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ChartIndicator(models.Model):
    '''
    Through model to store indicators
    '''
    chart = models.ForeignKey(IndicatorChartSetting, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    class Meta:
        unique_together = ('chart', 'indicator')

class ChartFilter(models.Model):
    '''
    Through model to store filter fields
    '''
    chart = models.ForeignKey(IndicatorChartSetting, on_delete=models.CASCADE, related_name='chart_for_filter')
    field = models.ForeignKey(ChartField, on_delete=models.CASCADE, related_name='chart_filter')
    value = models.CharField(max_length=100)
    class Meta:
        unique_together = ('chart', 'field', 'value')

class DashboardSetting(models.Model):
    '''
    Settings that control a dashboard, or a collection of charts. 
    '''
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='dashboard_settings')
    filters = models.ManyToManyField(ChartField, through='DashboardFilter', blank=True) #currently not used
    charts = models.ManyToManyField(IndicatorChartSetting, through='DashboardIndicatorChart', blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True) #filters all dashboard charts to a project
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True) #filters all dashboard charts to an organization
    cascade_organization = models.BooleanField(default=False) #if project/organization are provided, also includes data from child organizations
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    

class DashboardFilter(models.Model):
    '''
    Through model for dashboard filters. Not currently used.
    '''
    dashboard = models.ForeignKey(DashboardSetting, on_delete=models.CASCADE)
    field = models.ForeignKey(ChartField, on_delete=models.CASCADE, related_name='dashboard_filter')
    value = models.CharField(max_length=100)
    class Meta:
        unique_together = ('dashboard', 'field', 'value')

class DashboardIndicatorChart(models.Model):
    '''
    Through table that links a dashboard to a set of charts. Currently order/width/height is unused. 
    '''
    dashboard = models.ForeignKey(DashboardSetting, on_delete=models.CASCADE)
    chart = models.ForeignKey(IndicatorChartSetting, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    width = models.CharField(max_length=50, blank=True, null=True)
    height = models.CharField(max_length=50, blank=True, null=True)
    class Meta:
        unique_together = ('dashboard', 'chart')

class PivotTable(models.Model):
    '''
    Model for storing pivot table settings that a user can return to. Supports unlimited breakdowns and 
    scoping by period, project, organization, and filtering repeat onlys (for respondent indicators).
    '''
    name = models.CharField(max_length=255, null=True, blank=True)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True)
    cascade_organization = models.BooleanField(default=False) #will also include child organizations of the selected organization

    params = models.ManyToManyField(ChartField, through='PivotTableParam', blank=True)
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)
    repeat_only = models.BooleanField(default=False)
    repeat_n = models.PositiveIntegerField(blank=True, null=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='pivot_tables')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class PivotTableParam(models.Model):
    '''
    Through table for m2m field pivot table params.
    '''
    pivot_table = models.ForeignKey(PivotTable, on_delete=models.CASCADE)
    field = models.ForeignKey(ChartField, on_delete=models.CASCADE)

class LineList(models.Model):
    '''
    Model that stores information about a line list. Accepts project, organization, assessment, start, and end
    as filters. 
    '''
    name = models.CharField(max_length=255, null=True, blank=True)
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, null=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True)
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True)
    cascade_organization = models.BooleanField(default=False) #will also include child organizations of the selected organization if project/organization are provided
    start = models.DateField(null=True, blank=True)
    end = models.DateField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='line_lists')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)



class RequestLog(models.Model):
    '''
    Model that tracks api requests made.
    '''
    path = models.CharField(max_length=200)
    timestamp = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=10)
    status_code = models.IntegerField()
    response_time_ms = models.FloatField()
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)