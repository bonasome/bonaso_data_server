from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views import View
from django.db.models import Q
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics
from rest_framework.decorators import action
from rest_framework import status
from django.db import transaction
from users.restrictviewset import RoleRestrictedViewSet
from organizations.models import Organization
from projects.models import Project
from indicators.models import Indicator, IndicatorSubcategory
from django.contrib.auth import get_user_model
from analysis.serializers import DashboardSettingSerializer, DashboardSettingListSerializer, DashboardIndicatorChartSerializer
from analysis.models import DashboardSetting, IndicatorChartSetting, ChartField, DashboardIndicatorChart, ChartFilter
from events.models import DemographicCount
from datetime import date
import csv
from django.utils.timezone import now
from datetime import datetime
from analysis.utils import get_indicator_aggregate, prep_csv
from io import StringIO
User = get_user_model()

#we may potentially need to rethink the user perms if we have to link this to other sites
class AnalysisViewSet(RoleRestrictedViewSet):
    @action(detail=False, methods=["get"], url_path='aggregate/(?P<indicator_id>[^/.]+)')
    def indicator_aggregate(self, request, indicator_id=None):
        user = request.user
        if user.role not in ['client', 'admin', 'meofficer', 'manager']:
            return Response(
                {"detail": "You do not have permission to view aggregated counts."},
                status=status.HTTP_403_FORBIDDEN
            )
        indicator = Indicator.objects.filter(id=indicator_id).first()
        if not indicator:
            return Response(
                {"detail": "Please provide a valid indicator id to view aggregate counts."},
                status=status.HTTP_400_BAD_REQUEST
            )
        project_id = request.query_params.get('project')
        organization_id = request.query_params.get('organization')
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        project = Project.objects.filter(id=project_id).first() if project_id else None
        organization = Organization.objects.filter(id=organization_id) if organization_id else None

        params = {}
        for cat in ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy', 'subcategory']:
            params[cat] = request.query_params.get(cat) in ['true', '1']
        
        split = request.query_params.get('split')

        aggregate = get_indicator_aggregate(user, indicator, params, split, project, organization, start, end)
        return Response(
                {"counts": aggregate},
                status=status.HTTP_200_OK
            )
    
    @action(detail=False, methods=["get"], url_path='download-indicator-aggregate/(?P<indicator_id>[^/.]+)')
    def download_indicator_aggregate(self, request, indicator_id=None):
        user = request.user
        if user.role not in ['client', 'admin', 'meofficer', 'manager']:
            return Response(
                {"detail": "You do not have permission to view aggregated counts."},
                status=status.HTTP_403_FORBIDDEN
            )

        indicator = Indicator.objects.filter(id=indicator_id).first()
        if not indicator:
            return Response(
                {"detail": "Please provide a valid indicator id to view aggregate counts."},
                status=status.HTTP_400_BAD_REQUEST
            )

        params = {}
        for cat in ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy']:
            params[cat] = request.query_params.get(cat) in ['true', '1']
        split = request.query_params.get('split')
        aggregates = get_indicator_aggregate(user, indicator, params, split)

        if not aggregates:
            return Response(
                {"detail": "No aggregate data found for this indicator."},
                status=status.HTTP_404_NOT_FOUND
            )

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        filename = f'aggregates_{indicator.code}_{timestamp}.csv'

        
        rows = prep_csv(aggregates, params)
        fieldnames = rows[0]
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows[1:]:
            row_dict = dict(zip(fieldnames, row))
            writer.writerow(row_dict)

        response = HttpResponse(buffer.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    


class DashboardSettingViewSet(RoleRestrictedViewSet):
    serializer_class = DashboardSettingSerializer  # default

    def get_serializer_class(self):
        if self.action == 'list':
            return DashboardSettingListSerializer
        else:
            return DashboardSettingSerializer
        
    def get_queryset(self):
        return DashboardSetting.objects.filter(created_by=self.request.user)
    
    @action(detail=False, methods=['get'], url_path='meta')
    def get_dashboard_meta(self, request):
        chart_types = [t for t, _ in IndicatorChartSetting.ChartType.choices]
        chart_type_labels = [choice.label for choice in IndicatorChartSetting.ChartType]
        fields = [f for f, _ in ChartField.Field.choices]
        field_labels = [choice.label for choice in ChartField.Field]
        axes = [s for s, _ in IndicatorChartSetting.AxisOptions.choices]
        axis_labels = [choice.label for choice in IndicatorChartSetting.AxisOptions]
        
        return Response({
            'chart_types': chart_types,
            'chart_type_labels': chart_type_labels,
            'fields': fields,
            'field_labels': field_labels,
            'axes': axes,
            'axis_labels': axis_labels
        })

    @action(detail=True, methods=['patch'], url_path='charts')
    def create_update_chart(self, request, pk=None):
        dashboard = self.get_object()
        user = request.user
        existing_id = request.data.get('chart_id')
        indicator_id = request.data.get('indicator')
        indicator = Indicator.objects.filter(id=indicator_id).first()
        if not indicator:
            return Response(
                {"detail": "A valid indicator id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        chart_type = request.data.get('chart_type')
        if not chart_type:
            return Response(
                {"detail": "A valid chart type is required."},
                status=status.HTTP_400_BAD_REQUEST
            )
        legend = request.data.get('legend')
        axis = request.data.get('axis')
        stack = request.data.get('stack')
        use_target = str(request.data.get('use_target')).lower() in ['true', '1']
        tabular = str(request.data.get('tabular')).lower() in ['true', '1']
        order = request.data.get('order', 0)
        width = request.data.get('width')
        height = request.data.get('height')
        filters_map = request.data.get('filters', [])
        
        if legend == 'subcategory' and not indicator.subcategories.exists():
            legend=None
        if stack == 'subcategory' and not indicator.subcategories.exists():
            stack=None

        if legend and use_target:
                legend = None
        if stack and use_target:
            stack=None

        if existing_id:    
            chart_link = DashboardIndicatorChart.objects.filter(id=existing_id).first()
            chart = chart_link.chart
            chart.chart_type = chart_type
            chart.axis = axis
            chart.use_target = use_target
            chart.legend = legend
            chart.stack = stack
            chart.indicator = indicator
            chart.tabular = tabular
            ChartFilter.objects.filter(chart=chart).delete()
            chart.save()

            chart_link.width = width
            chart_link.height = height
            chart_link.order = order
            chart_link.save()

        else:
            chart = IndicatorChartSetting.objects.create(
                indicator = indicator,
                chart_type = chart_type,
                tabular = tabular,
                axis = axis,
                legend = legend,
                stack=stack,
                use_target = use_target,
                created_by=user,
            )
            chart_link = DashboardIndicatorChart.objects.create(
                dashboard=dashboard,
                chart = chart,
                width = width,
                height = height,
                order = order,
            )
        filters = []
        if filters_map:
            for field, values in filters_map.items():
                for val in values:
                    field_obj = ChartField.objects.get_or_create(name=field)[0]
                    fil = ChartFilter.objects.create(field=field_obj, value=val, chart=chart)
                    filters.append(fil)

        serializer = DashboardIndicatorChartSerializer(chart_link)
        return Response({"detail": f"Dashboard updated.", "chart_data": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['delete'], url_path='remove-chart/(?P<chart_link_id>[^/.]+)')
    def remove_chart(self, request, pk=None, chart_link_id=None):
        dashboard = self.get_object()
        user = request.user
        IndicatorChartSetting.objects.filter(id=chart_link_id).delete()
        return Response({"detail": f"Removed chart from dashboard.", "id": chart_link_id}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='breakdowns')
    def get_breakdowns_meta(self, request):
        breakdowns = {}

        # Loop over desired choice fields
        choice_fields = ['sex', 'age_range', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy']

        for field_name in choice_fields:
            field = DemographicCount._meta.get_field(field_name)
            if field.choices:
                breakdowns[field_name] = {
                    choice: label for choice, label in field.choices
                }

        return Response(breakdowns)
class IndicatorChartSettingViewSet(RoleRestrictedViewSet):
    serializer_class = IndicatorChartSetting
        
    def get_queryset(self):
        return IndicatorChartSetting.objects.filter(created_by=self.request.user)