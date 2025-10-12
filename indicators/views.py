from django.shortcuts import render, redirect
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.decorators import action

from users.restrictviewset import RoleRestrictedViewSet
from indicators.models import Indicator, Assessment, LogicCondition, LogicGroup
from indicators.serializers import IndicatorSerializer, Assessment, AssessmentSerializer, AssessmentListSerializer
from projects.models import Task, Target
from respondents.models import Interaction
from respondents.utils import get_enum_choices
from events.models import DemographicCount


class IndicatorViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IndicatorSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['assessment']
    ordering_fields = ['index']
    search_fields = ['name']    

    def get_queryset(self):
        queryset = Indicator.objects.all()
        user = self.request.user
        '''
        put perms here
        '''
        return queryset
    
    @action(detail=True, methods=['patch'], url_path='change-order')
    def change_order(self, request, pk=None):
        ind=self.get_object()
        user=request.user

        if user.role not in ['admin']:
            return Response(
                {'detail': 'You do not have permission to do this'},
                status=status.HTTP_403_FORBIDDEN
            )
        inds = list(Indicator.objects.filter(assessment=ind.assessment).exclude(id=ind.id).order_by('order'))
        total = len(inds) + 1  # +1 because we will insert `ind` itself

        try:
            pos = int(request.data.get('position'))
            print(pos)
        except (TypeError, ValueError):
            return Response({'detail': 'Position must be an integer'}, status=400)

        if not (0 <= pos < total):
            return Response(
                {'detail': f'Position must be between 0 and {total-1}'}, 
                status=400
            )
        inds.insert(pos, ind)
        print(inds)
        with transaction.atomic():
            for idx, i in enumerate(inds):
                i.order = idx
            Indicator.objects.bulk_update(inds, ['order'])
        return Response({'status': 'ok'}, status=200)
    

    @action(detail=False, methods=['get'], url_path='meta')
    def get_meta(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "type": get_enum_choices(Indicator.Type),
            "category": get_enum_choices(Indicator.Category),
            "group_operators": get_enum_choices(LogicGroup.Operator),
            "source_types": get_enum_choices(LogicCondition.SourceType),
            "respondent_fields": get_enum_choices(LogicCondition.RespondentField),
            "operators": get_enum_choices(LogicCondition.Operator),
            "respondent_choices": LogicCondition.RESPONDENT_VALUE_CHOICES
        })

class AssessmentViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IndicatorSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = []
    ordering_fields = ['name']
    search_fields = ['name'] 

    def get_queryset(self):
        queryset = Assessment.objects.all()
        user = self.request.user
        #expects organizations=1,2,3,4
        exclude_org_param = self.request.query_params.get('exclude_organization') 
        if exclude_org_param:
            ids = Task.objects.filter(organization_id=exclude_org_param).values_list('assessment_id', flat=True)
            queryset = queryset.exclude(id__in=ids)

        exclude_project_param = self.request.query_params.get('exclude_project')
        if exclude_project_param:
            ids = Task.objects.filter(project_id=exclude_project_param).values_list('assessment_id', flat=True)
            queryset = queryset.exclude(id__in=ids)
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return AssessmentListSerializer
        else:
            return AssessmentSerializer
