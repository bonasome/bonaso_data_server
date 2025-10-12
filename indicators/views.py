from django.shortcuts import render, redirect
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
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
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return AssessmentListSerializer
        else:
            return AssessmentSerializer
