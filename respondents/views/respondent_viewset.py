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
    '''
    Viewset for managing respondents
    '''
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, OrderingFilter]
    ordering_fields = ['last_name', 'first_name', 'village', 'district']
    search_fields = ['first_name', 'last_name', 'uuid', 'comments', 'village'] 
    filterset_fields = ['sex', 'age_range', 'district']
    serializer_class = RespondentSerializer

    def get_queryset(self):
        '''
        All users can see/edit all respondents
        '''
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
        '''
        Only admins can delete respondents, and not if the respondent has interactions associated with them.
        '''
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
    def get_meta(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "districts": get_enum_choices(Respondent.District),
            "sexs": get_enum_choices(Respondent.Sex),
            "age_ranges": get_enum_choices(Respondent.AgeRanges),
            "kp_types": get_enum_choices(KeyPopulation.KeyPopulations),
            "disability_types": get_enum_choices(DisabilityType.DisabilityTypes),
            "special_attributes": get_enum_choices(RespondentAttributeType.Attributes)
        })
    

    @action(detail=False, methods=['post'], url_path='mobile')
    def mobile_upload(self, request):
        '''
        Allow the mobile app to send a list of respondents and serialize them. 
        '''
        if request.user.role == 'client':
                raise PermissionDenied('You do not have permission to perform this action.')
        data = request.data
        if not isinstance(data, list):
            return Response({"detail": "Expected a list of respondents."}, status=400)
        ids_map = [] #returns a map of local_id and the created server_id so the app knows what was uploaded
        errors = []
        for item in data:
            try:
                server_id = item.get('server_id')
                id_no = item.get('id_no') #local ID
                existing = None
                if server_id:
                    existing = Respondent.objects.filter(id=server_id).first()
                elif id_no is not None: #skip for anon respondents that have no id_no
                    existing = Respondent.objects.filter(id_no=id_no).first()
                if existing: #auto update existing respondents (matched by ID no)
                    respondent_serializer = RespondentSerializer(
                        existing, data=item, context={'request': request}, partial=True
                    )
                else: #otherwise create new
                    respondent_serializer = RespondentSerializer(
                        data=item, context={'request': request}
                    )
                respondent_serializer.is_valid(raise_exception=True)
                respondent = respondent_serializer.save()
                ids_map.append({'local_id': item.get('local_id'), 'server_id': respondent.id })
            #catch and return any errors
            except Exception as err:
                errors.append({
                    'local_id': item.get('local_id'),
                    'message': str(err),
                })  
        return Response({
            "mappings": ids_map,
            "errors": errors
        }, status=status.HTTP_200_OK)