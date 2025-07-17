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
from events.models import Event, DemographicCount, EventTask, EventOrganization, CountFlag
from organizations.models import Organization
from projects.models import Project, Task
from indicators.models import Indicator, IndicatorSubcategory
from events.serializers import EventSerializer, DCSerializer
from django.contrib.auth import get_user_model
from collections import defaultdict
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
        for cat in ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy']:
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