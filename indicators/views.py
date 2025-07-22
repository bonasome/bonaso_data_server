from django.shortcuts import render, redirect
from django.forms.models import model_to_dict
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework.decorators import action
from indicators.models import Indicator, IndicatorSubcategory
from indicators.serializers import IndicatorSerializer, IndicatorListSerializer, ChartSerializer
from projects.models import Task
from respondents.models import Interaction
from rest_framework import status

class IndicatorViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Indicator.objects.all()
    serializer_class = IndicatorSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    ordering_fields = ['code', 'name']
    search_fields = ['name', 'code', 'description'] 

    def get_queryset(self):
        queryset = super().get_queryset() 
        user = self.request.user

        if user.role != 'admin':
            queryset = queryset.filter(status=Indicator.Status.ACTIVE)

        exclude_project_id = self.request.query_params.get('exclude_project')
        exclude_org_id = self.request.query_params.get('exclude_organization')

        if exclude_project_id:
            task_filter = {'project_id': exclude_project_id}
            if exclude_org_id:
                task_filter['organization_id'] = exclude_org_id

            bad_ids = Task.objects.filter(**task_filter).values_list('indicator__id', flat=True)
            queryset = queryset.exclude(id__in=bad_ids)

        return queryset

    @action(detail=False, methods=['get'], url_path='chart-data')
    def chart_data(self, request):
        queryset = self.get_queryset()

        # Optional filters from query parameters
        indicator_id = request.query_params.get('indicator')
        organization_id = request.query_params.get('organization')
        project_id = request.query_params.get('project')

        if indicator_id:
            queryset = queryset.filter(id=indicator_id)

        queryset = queryset.distinct()

        # Skip pagination
        self.pagination_class = None
        serializer = ChartSerializer(queryset, context={'organization_id': organization_id, 'project_id': project_id}, many=True)
        return Response(serializer.data)

    def paginate_queryset(self, queryset):
        # Disable pagination only for this specific action
        if self.action == 'chart_data':
            return None
        return super().paginate_queryset(queryset)
    
    def get_serializer_class(self):
        if self.action == 'list':
            return IndicatorListSerializer
        else:
            return IndicatorSerializer
        
    def create(self, request, *args, **kwargs):
        if request.user.role != 'admin':
            raise PermissionDenied("Only admins can create indicators.")
        return super().create(request, *args, **kwargs)
    
    def update(self, request, *args, **kwargs):
        if request.user.role != 'admin':
            raise PermissionDenied("Only admins can create indicators.")
        return super().update(request, *args, **kwargs)


    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user) 

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user) 

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        if user.role != 'admin':
            return Response(
                {"detail": "You do not have permission to delete an indicator."},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if instance.status == Indicator.Status.ACTIVE:
            return Response(
                {"detail": "You cannot delete an active indicator. Consider marking this as deprecated instead."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Prevent deletion if indicator has interactions
        if Interaction.objects.filter(task__indicator__id=instance.id).exists():
            return Response(
                {"detail": "You cannot delete an indicator that has interactions associated with it."},
                status=status.HTTP_400_BAD_REQUEST
            )

        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'], url_path='meta')
    def filter_options(self, request):
        from respondents.models import RespondentAttributeType
        statuses = [status for status, _ in Indicator.Status.choices]
        indicator_types = [t for t, _ in Indicator.IndicatorType.choices]
        indicator_type_labels = [t.label for t in Indicator.IndicatorType]
        required_attribute = [t for t, _ in RespondentAttributeType.Attributes.choices]
        required_attribute_labels = [t.label for t in RespondentAttributeType.Attributes]

        return Response({
            'statuses': statuses,
            'indicator_types': indicator_types,
            'indicator_type_labels': indicator_type_labels,
            'required_attributes': required_attribute,
            'required_attribute_labels': required_attribute_labels,
        })