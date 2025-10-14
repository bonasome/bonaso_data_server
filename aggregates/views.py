from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404

from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from rest_framework import status

from datetime import date
from django.utils.timezone import now
from collections import defaultdict

from users.restrictviewset import RoleRestrictedViewSet
from django.contrib.auth import get_user_model
User = get_user_model()

from events.models import Event, DemographicCount, EventTask, EventOrganization
from events.serializers import EventSerializer, DCSerializer
from events.utils import get_schema_key, make_key, count_flag_logic
from organizations.models import Organization
from aggregates.models import AggregateCount, AggregateGroup
from aggregates.serializers import AggregateCountSerializer, AggregatGroupSerializer
from projects.models import Task, ProjectOrganization
from respondents.utils import get_enum_choices


class AggregateViewSet(RoleRestrictedViewSet):
    queryset = AggregateGroup.objects.all().prefetch_related('counts')
    serializer_class = AggregatGroupSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = AggregateGroup.objects.all()
        
        #client can see any event that has counts relevent to their projects
        if user.role == 'client':
            queryset = queryset.filter(project__client=user.client_organization)

        #higher roles can see event where they are the host, their child is the host, or they are a participant
        elif user.role in ['meofficer', 'manager']:
            child_orgs=ProjectOrganization.objects.filter(parent_organization=user.organization)
            valid_ids = child_orgs.values_list('organization_id', flat=True)
            valid_projs = child_orgs.values_list('project_id', flat=True)
            queryset = queryset.filter(Q(organization=user.organization) |
                Q(organization_id__in=valid_ids, project_id__in=valid_projs)
            ).distinct()
        elif user.role != 'admin':
            return AggregateGroup.objects.none()
        
        return queryset.distinct()

    # Optional: override destroy to also remove related counts
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        if user.role != 'admin' and (instance.organization != user.organization or not
            ProjectOrganization.objects.filter(parent_organization=user.organization, project=instance.project, organization=instance.organization).exists()):
            raise PermissionDenied("You do not have permission to delete this aggregate group.")
        with transaction.atomic():
            AggregateCount.objects.filter(group=instance).delete()
            instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
