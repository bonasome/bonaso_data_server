from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from indicators.models import Indicator
from projects.models import Project
User = get_user_model()
class ChartField(models.Model):
    '''
    Shared enum storing model that handles controlled filter/legend/stack fields 
    (see the events.models --> Demogrpahic count for more).
    '''
    class Field(models.TextChoices):
        AR = 'age_range', _('Age Range')
        SEX = 'sex', _('Sex')
        KP ='kp_type', _('Key Population Type')
        DIS = 'disability_type', _('Disability Type')
        CIT = 'citizenship', _('Citizenship')
        HIV = 'hiv_status', _('HIV Status')
        PREG = 'pregnancy', ('Pregnancy')
        ORG = 'organization', ('Organization')
        SC = 'subcategory', ('Indicator Subcategory')
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
    All charts can also be filtered by the fields above. All charts can also include a data table.
    '''
    class ChartType(models.TextChoices):
        PIE = 'pie', _('Pie Chart')
        LINE = 'line', _('Line Chart')
        BAR = 'bar', _('Bar Chart')
    class AxisOptions(models.TextChoices):
        MONTH  = 'month', _('Month')
        QUARTER = 'quarter', _('Quarter')
    
    
    indicators = models.ManyToManyField(Indicator, through='ChartIndicator')
    chart_type = models.CharField(max_length=25, choices=ChartType.choices, default=ChartType.BAR, null=True, blank=True)
    tabular = models.BooleanField(default=False) #also show a data table
    axis = models.CharField(max_length=25, choices=AxisOptions.choices, default=AxisOptions.QUARTER, null=True, blank=True)
    legend = models.CharField(max_length=25, choices=ChartField.Field.choices, default=None, null=True, blank=True)
    stack = models.CharField(max_length=25, choices=ChartField.Field.choices, default=None, null=True, blank=True)
    use_target = models.BooleanField(default=False) #determines whether or not to show targets (will disable legend/stack)
    filters = models.ManyToManyField(ChartField, through='ChartFilter', blank=True, related_name='chart_filters')
    
    #seperate date filters not linked to fields
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='chart_settings_created_by')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class ChartIndicator(models.Model):
    chart = models.ForeignKey(IndicatorChartSetting, on_delete=models.CASCADE)
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE)
    class Meta:
        unique_together = ('chart', 'indicator')

class ChartFilter(models.Model):
    chart = models.ForeignKey(IndicatorChartSetting, on_delete=models.CASCADE, related_name='chart_for_filter')
    field = models.ForeignKey(ChartField, on_delete=models.CASCADE, related_name='chart_filter')
    value = models.CharField(max_length=100)
    class Meta:
        unique_together = ('chart', 'field', 'value')

class DashboardSetting(models.Model):
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='dashboard_settings')
    filters = models.ManyToManyField(ChartField, through='DashboardFilter', blank=True)
    charts = models.ManyToManyField(IndicatorChartSetting, through='DashboardIndicatorChart', blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    

class DashboardFilter(models.Model):
    dashboard = models.ForeignKey(DashboardSetting, on_delete=models.CASCADE)
    field = models.ForeignKey(ChartField, on_delete=models.CASCADE, related_name='dashboard_filter')
    value = models.CharField(max_length=100)
    class Meta:
        unique_together = ('dashboard', 'field', 'value')

class DashboardIndicatorChart(models.Model):
    dashboard = models.ForeignKey(DashboardSetting, on_delete=models.CASCADE)
    chart = models.ForeignKey(IndicatorChartSetting, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    width = models.CharField(max_length=50, blank=True, null=True)
    height = models.CharField(max_length=50, blank=True, null=True)
    class Meta:
        unique_together = ('dashboard', 'chart')