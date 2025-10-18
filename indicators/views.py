from django.shortcuts import render, redirect
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q
from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.decorators import action

from users.restrictviewset import RoleRestrictedViewSet
from indicators.models import Indicator, Assessment, LogicCondition, LogicGroup
from indicators.serializers import IndicatorSerializer, Assessment, AssessmentSerializer, AssessmentListSerializer
from projects.models import Task, Target
from respondents.models import Response as ResponseObject, Interaction
from aggregates.models import AggregateGroup
from respondents.utils import get_enum_choices


class IndicatorViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = IndicatorSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['assessment', 'category']
    ordering_fields = ['index']
    search_fields = ['name']    

    def get_queryset(self):
        queryset = Indicator.objects.all()
        user = self.request.user
        '''
        put perms here
        '''
        project_param = self.request.query_params.get('project')
        if project_param:
            direct_indicators = Task.objects.filter(
                indicator__isnull=False, 
                project_id=project_param
            ).values_list('indicator_id', flat=True)

            # Assessments linked to tasks
            assessment_ids = Task.objects.filter(
                assessment__isnull=False, 
                project_id=project_param
            ).values_list('assessment_id', flat=True)

            # Indicators that belong to those assessments
            assessment_indicators = Indicator.objects.filter(
                assessment_id__in=assessment_ids
            ).values_list('id', flat=True)
            valid_ids = list(direct_indicators) + list(assessment_indicators)
            queryset = queryset.filter(id__in=valid_ids)
        
        org_param = self.request.query_params.get('organization')
        if org_param:
            direct_indicators = Task.objects.filter(
                indicator__isnull=False, 
                organization_id=org_param
            ).values_list('indicator_id', flat=True)

            # Assessments linked to tasks
            assessment_ids = Task.objects.filter(
                assessment__isnull=False, 
                organization_id=org_param
            ).values_list('assessment_id', flat=True)

            # Indicators that belong to those assessments
            assessment_indicators = Indicator.objects.filter(
                assessment_id__in=assessment_ids
            ).values_list('id', flat=True)
            valid_ids = list(direct_indicators) + list(assessment_indicators)
            queryset = queryset.filter(id__in=valid_ids)
        
        agg_param = self.request.query_params.get('allow_aggregate')
        if agg_param:
            agg_param = agg_param in ['true', '1']
            queryset = queryset.filter(allow_aggregate=agg_param)
        
        exclude_cat_param = self.request.query_params.get('exclude_category')
        if exclude_cat_param:
            queryset = queryset.exclude(category=exclude_cat_param)
        
        cat_param = self.request.query_params.get('category')
        if cat_param:
            queryset = queryset.filter(category=cat_param)

        exclude_org_param = self.request.query_params.get('exclude_organization')
        exclude_project_param = self.request.query_params.get('exclude_project') 
        if exclude_org_param and exclude_project_param:
            ids = Task.objects.filter(indicator__isnull=False, organization_id=exclude_org_param, project_id=exclude_project_param).values_list('indicator_id', flat=True)
            print(ids)
            queryset = queryset.exclude(id__in=ids)

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
    
    def destroy(self, request, *args, **kwargs):
        '''
        Only admins can delete indicators, and not if the respondent has interactions associated with them.
        '''
        user = request.user
        instance = self.get_object()

        # Prevent deletion if respondent has interactions
        if ResponseObject.objects.filter(indicator_id=instance.id).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an indicator that has an interaction associated with them. "
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        if AggregateGroup.objects.filter(indicator_id=instance.id).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an indicator that has an aggregate count associated with it. "
                    )
                },
                status=status.HTTP_409_CONFLICT
            )
        
        if Target.objects.filter(indicator_id=instance.id).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an assessment that has a target associated with it. "
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        # Permission check: only admin can delete
        if user.role != 'admin':
            return Response(
                {"detail": "You do not have permission to delete this item."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Perform deletion
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

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
            "respondent_choices": LogicCondition.RESPONDENT_VALUE_CHOICES,
            "condition_types": get_enum_choices(LogicCondition.ExtraChoices),
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
        exclude_project_param = self.request.query_params.get('exclude_project') 
        if exclude_org_param and exclude_project_param:
            ids = Task.objects.filter(assessment__isnull=False, organization_id=exclude_org_param, project_id=exclude_project_param).values_list('assessment_id', flat=True)
            print(ids)
            queryset = queryset.exclude(id__in=ids)

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return AssessmentListSerializer
        else:
            return AssessmentSerializer

    def destroy(self, request, *args, **kwargs):
        '''
        Only admins can delete indicators, and not if the respondent has interactions associated with them.
        '''
        user = request.user
        if user.role != 'admin':
            return Response(
                {"detail": "You do not have permission to delete this item."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        instance = self.get_object()

        # Prevent deletion if respondent has interactions
        if Interaction.objects.filter(assessment_id=instance.id).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an assessment that has an interaction associated with them. "
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        if AggregateGroup.objects.filter(indicator__assessment_id=instance.id).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an assessment that has an aggregate count associated with it. "
                    )
                },
                status=status.HTTP_409_CONFLICT
            )
        if Target.objects.filter(indicator__assessment_id=instance.id).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete an assessment that has a target associated with it. "
                    )
                },
                status=status.HTTP_409_CONFLICT
            )
        
        # Perform deletion
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)