from django.shortcuts import render, redirect
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.decorators import action

from users.restrictviewset import RoleRestrictedViewSet
from indicators.models import Indicator
from indicators.serializers import IndicatorSerializer, IndicatorListSerializer
from projects.models import Task, Target
from respondents.models import Interaction
from respondents.utils import get_enum_choices
from events.models import DemographicCount

class IndicatorViewSet(RoleRestrictedViewSet):
    '''
    Viewset that manages everything related to indicators, mostly only ever used by admins or for task creation/data analysis,
    since otherwise non-admins should interact with indicators primarily though tasks. 
    '''
    permission_classes = [IsAuthenticated]
    serializer_class = IndicatorSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'indicator_type']
    ordering_fields = ['code', 'name']
    search_fields = ['name', 'code', 'description'] 

    def get_queryset(self):
        queryset = Indicator.objects.all()
        user = self.request.user
        #check perms
        if user.role == 'client':
            queryset = queryset.filter(status=Indicator.Status.ACTIVE)
            valid_ids = Task.objects.filter(project__client=user.client_organization).values_list('indicator__id', flat=True)
            queryset = queryset.filter(id__in=valid_ids)
        if user.role in ['meofficer', 'manager']:
            queryset = queryset.filter(status=Indicator.Status.ACTIVE)
            valid_ids = Task.objects.filter(organization=user.organization).values_list('indicator__id', flat=True)
            queryset = queryset.filter(id__in=valid_ids)

        #exclude certain projects/orgs for when assigning tasks
        exclude_project_id = self.request.query_params.get('exclude_project')
        exclude_org_id = self.request.query_params.get('exclude_organization')

        if exclude_project_id:
            task_filter = {'project_id': exclude_project_id}
            if exclude_org_id:
                task_filter['organization_id'] = exclude_org_id

            bad_ids = Task.objects.filter(**task_filter).values_list('indicator__id', flat=True)
            queryset = queryset.exclude(id__in=bad_ids)

        return queryset
    
    def get_serializer_class(self):
        if self.action == 'list':
            return IndicatorListSerializer
        else:
            return IndicatorSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user) 

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user) 


    def destroy(self, request, *args, **kwargs):
        '''
        Only allow destroy for inactive indicators that have no interactions attached.
        '''
        user = request.user
        instance = self.get_object()

        if user.role != 'admin':
            return Response(
                {"detail": "You do not have permission to delete an indicator."},
                status=status.HTTP_403_FORBIDDEN
            )
        #prevent deletion of active indicators
        if instance.status == Indicator.Status.ACTIVE:
            return Response(
                {"detail": "You cannot delete an active indicator. Consider marking this as deprecated instead."},
                status=status.HTTP_409_CONFLICT
            )
        # Prevent deletion if indicator has interactions
        if Interaction.objects.filter(task__indicator__id=instance.id).exists():
            return Response(
                {"detail": "You cannot delete an indicator that has interactions associated with it."},
                status=status.HTTP_409_CONFLICT
            )
        # or if it has linked counts
        if DemographicCount.objects.filter(task__indicator__id=instance.id).exists():
            return Response(
                {"detail": "You cannot delete an indicator that has counts associated with it."},
                status=status.HTTP_409_CONFLICT
            )
        #or if it has linked targets
        if Target.objects.filter(task__indicator=instance).exists():
            return Response(
                {"detail": "You cannot delete an indicator that has targets associated with it."},
                status=status.HTTP_409_CONFLICT
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='meta')
    def get_meta(self, request):
        from respondents.models import RespondentAttributeType
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "statuses": get_enum_choices(Indicator.Status),
            "indicator_types": get_enum_choices(Indicator.IndicatorType),
            "required_attributes": get_enum_choices(RespondentAttributeType.Attributes)
        })