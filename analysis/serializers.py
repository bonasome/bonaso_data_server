from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from analysis.models import DashboardFilter, ChartField, IndicatorChartSetting, DashboardSetting, DashboardIndicatorChart, ChartFilter
from analysis.utils import get_indicator_aggregate, get_target_aggregates
from projects.serializers import ProjectListSerializer, Target
from indicators.serializers import IndicatorListSerializer
from events.models import DemographicCount
from collections import defaultdict


class IndicatorChartSerializer(serializers.ModelSerializer):
    chart_data = serializers.SerializerMethodField(read_only=True)
    targets = serializers.SerializerMethodField(read_only=True)
    indicator = IndicatorListSerializer(read_only=True)
    filters = serializers.SerializerMethodField(read_only=True)
    allow_targets = serializers.SerializerMethodField(read_only=True) #simple helper var to help the frontend determine whether or not to shown the option, cause no one wants that crap where you select an option and its like screw you, there's not data here. Get pranked, nerd
    def get_chart_data(self, obj):
        params = {}
        for cat in ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy', 'subcategory']:
            params[cat] = (cat == obj.legend) or (cat == obj.stack)
        filters = self.get_filters(obj)
        aggr  = get_indicator_aggregate(user=obj.created_by, indicator=obj.indicator, params=params, split=obj.axis, start=obj.start_date, end=obj.end_date, filters=filters)
        return aggr
    
    def get_filters(self, obj):
        queryset = ChartFilter.objects.filter(chart=obj)
        filters = defaultdict(list)
        for fi in queryset:
            filters[fi.field.name].append(fi.value)
        print(filters)
        return filters
    
    def get_allow_targets(self, obj):
        return Target.objects.filter(task__indicator=obj.indicator).exists()
    
    def get_targets(self, obj):
        if not obj.use_target:
            return {}
        targets = get_target_aggregates(obj.created_by, indicator=obj.indicator, split=obj.axis, start=obj.start_date, end=obj.end_date)
        return targets
    class Meta:
        model = IndicatorChartSetting
        fields = ['id', 'indicator', 'created_by', 'tabular', 'axis', 'legend', 'stack', 'chart_type', 'use_target',
                  'start_date', 'end_date', 'chart_data', 'allow_targets', 'targets', 'filters']


class DashboardFilterSerializer(serializers.ModelSerializer):
    field = serializers.SlugRelatedField(slug_field="name", queryset=ChartField.objects.all())

    class Meta:
        model = DashboardFilter
        fields = ['field', 'value']

class DashboardIndicatorChartSerializer(serializers.ModelSerializer):
    chart = IndicatorChartSerializer(read_only=True)

    class Meta:
        model = DashboardIndicatorChart
        fields = ['id', 'chart', 'width', 'height', 'order']

class DashboardSettingListSerializer(serializers.ModelSerializer):
    project = ProjectListSerializer()
    class Meta:
        model = DashboardSetting
        fields = ['id', 'name', 'description', 'project']

class DashboardSettingSerializer(serializers.ModelSerializer):
    filters = DashboardFilterSerializer(source='dashboardfilter_set', many=True, required=False, allow_null=True)
    indicator_charts = DashboardIndicatorChartSerializer(source='dashboardindicatorchart_set', required=False, many=True, allow_null=True)

    class Meta:
        model = DashboardSetting
        fields = ['id', 'name', 'description', 'created_by', 'filters','created_at', 'updated_at','indicator_charts']
        read_only_fields = ['created_by', 'created_at', 'updated_at']

    def create(self, validated_data):
        filters_data = validated_data.pop('dashboardfilter_set', [])
        charts_data = validated_data.pop('dashboardindicatorchart_set', [])
        dashboard = DashboardSetting.objects.create(created_by=self.context['request'].user, **validated_data)
        return dashboard
