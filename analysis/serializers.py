from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from analysis.models import DashboardFilter, ChartField, IndicatorChartSetting, DashboardSetting, DashboardIndicatorChart, ChartFilter, PivotTable, PivotTableParam, LineList, RequestLog
from analysis.utils.aggregates import  aggregates_switchboard
from analysis.utils.targets import get_target_aggregates
from analysis.utils.csv import prep_csv
from analysis.utils.line_list import prep_line_list
from organizations.models import Organization
from organizations.serializers import OrganizationListSerializer
from projects.models import Project
from projects.serializers import ProjectListSerializer, Target
from profiles.serializers import ProfileListSerializer
from indicators.models import Indicator
from indicators.serializers import IndicatorSerializer
from events.models import DemographicCount
from collections import defaultdict
from respondents.models import Interaction

class LineListListSerializer(serializers.ModelSerializer):
    '''
    Returns list of a user's line lists for view in an index component
    '''
    class Meta:
        model = LineList
        fields = ['id', 'name']

class LineListSerializer(serializers.ModelSerializer):
    '''
    Returns detailed data about a line list and allows for the user to create a new line list. 
    '''
    indicator = IndicatorSerializer(read_only=True)
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), write_only=True, source='indicator', allow_null=True, required=False)
    organization = OrganizationListSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization', allow_null=True, required=False)
    project = ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, source='project', allow_null=True, required=False)
    data = serializers.SerializerMethodField()

    def get_data(self, obj):
        '''
        Get list of objects containing information about each row of the line list
        '''
        return prep_line_list(
            user=obj.created_by,
            indicator=obj.indicator,
            project=obj.project,
            organization=obj.organization,
            start=obj.start, 
            end=obj.end, 
            cascade=obj.cascade_organization,
        )
    class Meta:
        model=LineList
        fields = [
            'id', 'name', 'project', 'project_id', 'organization', 'organization_id',
            'indicator', 'indicator_id', 'start', 'end', 'cascade_organization', 'data'
        ]
    def create(self, validated_data):
        user = self.context.get('request').user if self.context.get('request') else None
        ll = LineList.objects.create(created_by=user, **validated_data)
        return ll
    

class PivotTableListSerializer(serializers.ModelSerializer):
    '''
    Returns list of a user's pivot tables for view in an index component
    '''
    display_name = serializers.SerializerMethodField()
    def get_display_name(self, obj):
        if obj.name:
            return obj.name
        params = [str(ChartField.Field(param.name).label) for param in obj.params.all()]
        clause = f' by '+', '.join(params) if params else ''
        return f'Pivot Table for Indicator {str(obj.indicator)}{clause}'

    class Meta:
        model = PivotTable
        fields = ['id', 'display_name',]

class PivotTableSerializer(serializers.ModelSerializer):
    '''
    Contains data for the pivot table and allows a user to create a new pivot table.
    '''
    indicator = IndicatorSerializer(read_only=True)
    indicator_id = serializers.PrimaryKeyRelatedField(queryset=Indicator.objects.all(), write_only=True, source='indicator', allow_null=True, required=False)
    organization = OrganizationListSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization', allow_null=True, required=False)
    project = ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, source='project', allow_null=True, required=False)
    params = serializers.SerializerMethodField()
    param_names = serializers.ListField(
        child=serializers.CharField(),
        write_only=True,
        allow_empty=True,
        required=False
    )
    display_name = serializers.SerializerMethodField()
    data = serializers.SerializerMethodField()

    def get_data(self, obj):
        '''
        Get data based on the pivot table settings.
        '''
        table_params = [param.name for param in obj.params.all()]
        #determine what params/breakdowns the user wants and format them as an object
        params = {}
        for cat in ['id', 'age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy', 'subcategory', 'platform', 'metric']:
            params[cat] = cat in table_params

        #collec the aggregates
        data = aggregates_switchboard(
            obj.created_by, 
            indicator=obj.indicator, 
            params=params, 
            project=obj.project,
            organization=obj.organization,
            start=obj.start, 
            end=obj.end, 
            repeat_only=obj.repeat_only, 
            n=obj.repeat_n,
            cascade=obj.cascade_organization
        )
        #convert it to a format with one param as the column headers, like one would expect a pivot table to look
        return prep_csv(aggregates=data, params=params)

    def get_params(self, obj):
        return [param.name for param in obj.params.all()]
    
    def get_display_name(self, obj):
        if obj.name:
            return obj.name
        params = [str(ChartField.Field(param.name).label) for param in obj.params.all()]
        clause = f' by '+', '.join(params) if params else ''
        return f'Pivot Table for Indicator {str(obj.indicator)}{clause}'
    
    class Meta:
        model = PivotTable
        fields = [
            'id', 'name', 'display_name', 'project', 'project_id', 'organization', 'organization_id', 'start', 'end', 'params', 
            'param_names', 'data', 'repeat_only', 'repeat_n', 'cascade_organization', 'indicator', 'indicator_id'
        ]

    def _update_params(self, table, params):
        '''
        Helper function that will accept a list of params and update the m2m field that manages the 
        tables params. 
        '''
        fields = []
        valid_names = [choice[0] for choice in ChartField.Field.choices]
        for param in params:
            if param in valid_names:
                field, created = ChartField.objects.get_or_create(name=param)
                fields.append(field)
        table.params.set(fields)
        table.save()
        return table
    
    def create(self, validated_data):
        param_names = validated_data.pop('param_names', [])
        user = self.context.get('request').user if self.context.get('request') else None
        table = PivotTable.objects.create(created_by=user, **validated_data)
        self._update_params(table, param_names)
        return table
    
    def update(self, instance, validated_data):
        param_names = validated_data.pop('param_names', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        self._update_params(instance, param_names)
        return instance
    
class IndicatorChartSerializer(serializers.ModelSerializer):
    '''
    Returns information about a chart as well as the data used to build the chart.
    '''
    chart_data = serializers.SerializerMethodField(read_only=True)
    targets = serializers.SerializerMethodField(read_only=True)
    indicators = IndicatorSerializer(read_only=True, many=True)
    filters = serializers.SerializerMethodField(read_only=True)
    allow_targets = serializers.SerializerMethodField(read_only=True) #simple helper var to help the frontend determine whether or not to shown the option, cause no one wants that crap where you select an option and its like screw you, there's not data here. Get pranked, nerd
    display_name = serializers.SerializerMethodField(read_only=True)
    def get_chart_data(self, obj):
        '''
        Collect data that will be used in the chart
        '''
        #based on legend/stack, get list of params to break the data down by
        params = {}
        for cat in ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy', 'subcategory', 'platform', 'metric', 'organization']:
            params[cat] = (cat == obj.legend) or (cat == obj.stack)
        # collect model filters
        filters = self.get_filters(obj)
        #get information from the dashboard about any meta filters (see below)
        project = self.context.get('project')
        organization = self.context.get('organization')
        cascade = self.context.get('cascade_organization', False)
        data={} # dict to store chart data

        #if only one indicator, return the aggreagate
        if obj.indicators.count() == 1:
            return aggregates_switchboard(obj.created_by, 
                indicator=obj.indicators.first(), 
                params=params, 
                split=obj.axis, 
                project=project,
                organization=organization,
                start=obj.start, 
                end=obj.end, 
                filters=filters, 
                repeat_only=obj.repeat_only, 
                n=obj.repeat_n,
                cascade=cascade
            )
        #if multiple indicators, return an array of indicators (no params should be present)
        data = []
        for indicator in obj.indicators.all():
            ind = aggregates_switchboard(
                obj.created_by,
                indicator=indicator,
                params=params,
                split=obj.axis,
                project=project,
                organization=organization,
                start=obj.start,
                end=obj.end,
                filters=filters,
                cascade=cascade
            )
            # the indicator will be used as the legend item
            for period, item in ind.items():
                row = {
                    'period': item.get('period', None),
                    'count': item.get('count', 0),
                    'indicator': str(indicator)
                }
                data.append(row)
        #return the array
        return {i: item for i, item in enumerate(data)}

    # build the filters dict
    def get_filters(self, obj):
        queryset = ChartFilter.objects.filter(chart=obj)
        filters = defaultdict(list)
        for fi in queryset:
            filters[fi.field.name].append(fi.value)
        return filters
    
    def get_allow_targets(self, obj):
        return Target.objects.filter(task__indicator__in=obj.indicators.all()).exists()
    
    #collect related target data
    def get_targets(self, obj):
        if not obj.use_target:
            return []
        targets = []
        project = self.context.get('project')
        organization = self.context.get('organization')
        for indicator in obj.indicators.all():
            target = get_target_aggregates(obj.created_by, indicator=indicator, split=obj.axis, project=project, organization=organization, start=obj.start, end=obj.end)
            targets.append(target)
        return targets
    
    def get_display_name(self, obj):
        if obj.name:
            return obj.name
        plural = 'Indicators' if obj.indicators.count() > 1 else 'Indicator'
        return f'Tracking {plural} {", ".join([str(ind) for ind in obj.indicators.all()])}'
    class Meta:
        model = IndicatorChartSetting
        fields = ['id', 'indicators', 'created_by', 'tabular', 'axis', 'legend', 'stack', 'chart_type', 'use_target',
                  'start', 'end', 'chart_data', 'allow_targets', 'targets', 'filters', 'repeat_only', 'repeat_n', 'name',
                  'display_name']


class DashboardFilterSerializer(serializers.ModelSerializer):
    '''
    Serializer for dashboard filters. Currently not in use. 
    '''
    field = serializers.SlugRelatedField(slug_field="name", queryset=ChartField.objects.all())

    class Meta:
        model = DashboardFilter
        fields = ['field', 'value']

class DashboardIndicatorChartSerializer(serializers.ModelSerializer):
    '''
    M2M serializer that links an indicator chart to the dashboard. Also passes filter information 
    (project, organization, cascade) to the chart when it collects data. 
    '''
    chart = serializers.SerializerMethodField()

    def get_chart(self, obj):
        #pass dashboard level context to the chart for when it collects data
        return IndicatorChartSerializer(
            obj.chart,
            context={
                **self.context,
                'organization': obj.dashboard.organization,
                'cascade_organization': obj.dashboard.cascade_organization,
                'project': obj.dashboard.project,
            }
        ).data

    class Meta:
        model = DashboardIndicatorChart
        fields = ['id', 'chart', 'width', 'height', 'order']

class DashboardSettingListSerializer(serializers.ModelSerializer):
    '''
    Get lightweight list of all of a user's dashboards for use in an index component. 
    '''
    project = ProjectListSerializer()
    class Meta:
        model = DashboardSetting
        fields = ['id', 'name', 'description', 'project']

class DashboardSettingSerializer(serializers.ModelSerializer):
    '''
    Detailed information about a dashboard that also contains the charts and chart data. 
    '''
    filters = DashboardFilterSerializer(source='dashboardfilter_set', many=True, required=False, allow_null=True)
    indicator_charts = DashboardIndicatorChartSerializer(source='dashboardindicatorchart_set', required=False, many=True, allow_null=True)
    organization = OrganizationListSerializer(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all(), write_only=True, source='organization', allow_null=True, required=False)
    project = ProjectListSerializer(read_only=True)
    project_id = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all(), write_only=True, source='project', allow_null=True, required=False)
    class Meta:
        model = DashboardSetting
        fields = ['id', 'name', 'description', 'created_by', 'filters','created_at', 'updated_at','indicator_charts', 'project', 
                  'organization', 'cascade_organization', 'project_id', 'organization_id']
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def create(self, validated_data):
        filters_data = validated_data.pop('dashboardfilter_set', [])
        charts_data = validated_data.pop('dashboardindicatorchart_set', [])
        dashboard = DashboardSetting.objects.create(created_by=self.context['request'].user, **validated_data)
        return dashboard

class RequestLogSerializer(serializers.ModelSerializer):
    '''
    Simple seializer that creates a serialized request log (URL, timestamp, status)
    '''
    user = ProfileListSerializer(read_only=True)
    class Meta:
        model=RequestLog
        fields = [
            'id', 'timestamp', 'path', 'method', 'status_code', 'response_time_ms', 'user'
        ]