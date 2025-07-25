from django.shortcuts import render, redirect
from django.db import transaction
from django.db.models import Q
from django.conf import settings

from rest_framework import filters, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework import serializers
from rest_framework.filters import SearchFilter
from rest_framework.decorators import action

from dateutil.parser import parse as parse_date
from datetime import date

import traceback

from users.restrictviewset import RoleRestrictedViewSet

from projects.models import Task
from respondents.models import Respondent, Interaction, HIVStatus, KeyPopulation, DisabilityType, RespondentAttributeType
from respondents.serializers import RespondentSerializer, RespondentListSerializer, InteractionSerializer
from respondents.utils import get_enum_choices

today = date.today().isoformat()

class RespondentViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, OrderingFilter]
    ordering_fields = ['last_name', 'first_name', 'village', 'district']
    search_fields = ['first_name', 'last_name', 'uuid', 'comments', 'village'] 
    filterset_fields = ['sex', 'age_range', 'district']
    serializer_class = RespondentSerializer

    def get_queryset(self):
        #respondents are 'public' since everyone will need to access them
        queryset = Respondent.objects.all()
        sex = self.request.query_params.get('sex')
        district = self.request.query_params.get('district')
        age_range = self.request.query_params.get('age_range')

        if sex:
            queryset = queryset.filter(sex=sex)
        if district:
            queryset = queryset.filter(district=district)
        if age_range:
            queryset = queryset.filter(age_range=age_range)

        return queryset
    
    def get_serializer_class(self):
        #return reduced serializer for index views
        if self.action == 'list':
            return RespondentListSerializer
        else:
            return RespondentSerializer

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        # Prevent deletion if respondent has interactions
        if Interaction.objects.filter(respondent_id=instance.id).exists():
            return Response(
                {
                    "detail": (
                        "You cannot delete a respondent that has interactions associated with them. "
                        "If this respondent has requested data removal, consider marking them as anonymous."
                    )
                },
                status=status.HTTP_409_CONFLICT
            )

        # Permission check: only admin can delete
        if user.role != 'admin':
            return Response(
                {"detail": "You do not have permission to delete this respondent."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Perform deletion
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


    @action(detail=False, methods=['get'], url_path='meta')
    def filter_options(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "districts": get_enum_choices(Respondent.District),
            "sexs": get_enum_choices(Respondent.Sex),
            "age_ranges": get_enum_choices(Respondent.AgeRanges),
            "kp_types": get_enum_choices(KeyPopulation.KeyPopulations),
            "disability_types": get_enum_choices(DisabilityType.DisabilityTypes),
            "special_attributes": get_enum_choices(
                RespondentAttributeType.Attributes,
                exclude={
                    RespondentAttributeType.Attributes.PLWHIV,
                    RespondentAttributeType.Attributes.KP,
                    RespondentAttributeType.Attributes.PWD,
                }
            )
        })
    
    @action(detail=False, methods=['post'], url_path='bulk')
    def bulk_upload(self, request):
        '''
        This is specifically designed for the mobile app, which for offline sync uploads in batches
        from a table.
        '''
        if request.user.role == 'client':
                raise PermissionDenied('You do not have permission to perform this action.')
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list of respondents."}, status=400)

        created_ids = []
        local_ids = []
        errors = []
        for i, item in enumerate(data):
            try:
                interactions = item.pop("interactions", [])

                #check if the respondent exists, then create/update based on that
                id_no = item.get('id_no')
                existing = None
                if id_no is not None:
                    existing = Respondent.objects.filter(id_no=id_no).first()
                if existing:
                    respondent_serializer = RespondentSerializer(
                        existing, data=item, context={'request': request}, partial=True
                    )
                else:
                    respondent_serializer = RespondentSerializer(
                        data=item, context={'request': request}
                    )
                respondent_serializer.is_valid(raise_exception=True)
                respondent = respondent_serializer.save(created_by=request.user)

                # Save interactions
                with transaction.atomic():
                    for interaction in interactions:
                        try:
                            interaction_date = interaction.get('interaction_date')
                            if not interaction_date:
                                raise ValidationError({'interaction_date': 'Interaction date is required'})
                            interaction_location = interaction.get('interaction_location') or None
                            subcats = interaction.get("subcategories_data", [])
                            task_id = interaction.get("task")
                            numeric_component = interaction.get('numeric_component')
                            try:
                                task_instance = Task.objects.get(id=task_id)
                            except Task.DoesNotExist:
                                raise ValidationError({"task": f"Task with ID {task_id} not found"})
                            lookup_fields = {
                                'respondent': respondent,
                                'interaction_date': interaction_date,
                                'task': task_id,
                            }
                            # Try to fetch the existing interaction, if it exists update it
                            instance = Interaction.objects.filter(**lookup_fields).first()

                            # Pass instance to serializer if it exists (update), otherwise it will create
                            serializer = InteractionSerializer(
                                instance=instance,
                                data={
                                    'respondent': respondent.id,
                                    'interaction_date': interaction_date,
                                    'interaction_location': interaction_location,
                                    'task': task_id,
                                    'numeric_component': numeric_component,
                                    'subcategories_data': subcats,
                                    'comments': '',
                                },
                                context={'request': request, 'respondent': respondent}
                            )
                            serializer.is_valid(raise_exception=True)
                            serializer.save()
                        except Exception as inter_err:
                            errors.append({
                                'respondent': respondent.id,
                                'interaction_error': str(inter_err),
                                'interaction_traceback': traceback.format_exc(),
                                'interaction_data': interaction
                            })
            
                local_ids.append(item.get('local_id'))
                created_ids.append(respondent.id)

            except ValidationError as ve:
                errors.append({
                    'index': i,
                    'error': 'Validation error',
                    'details': ve.detail,
                    'data': item
                })
            except Exception as e:
                errors.append({
                    'index': i,
                    'error': str(e),
                    'data': item
                })
        return Response({
            "created_ids": created_ids,
            "local_ids": local_ids,
            "errors": errors
        }, status=status.HTTP_207_MULTI_STATUS if errors else status.HTTP_201_CREATED)