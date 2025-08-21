from django.shortcuts import render, redirect
from django.db.models import Q

from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action

from users.restrictviewset import RoleRestrictedViewSet

from social.models import SocialMediaPost
from social.serializers import SocialMediaPostSerializer
from projects.models import ProjectOrganization
from respondents.utils import get_enum_choices

class SocialMediaPostViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    queryset = SocialMediaPost.objects.all()
    serializer_class = SocialMediaPostSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['platform']
    ordering_fields = ['published_at', 'created_at']
    search_fields = ['name', 'platform', 'description']

    def get_queryset(self):

        user = self.request.user

        queryset = SocialMediaPost.objects.all()

        if user.role == 'admin':
            queryset = queryset
        elif user.role == 'client':
            queryset = queryset.filter(tasks__project__client=user.client_organization).distinct()
        elif user.role in ['meofficer', 'manager']:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            queryset = queryset.filter(
                Q(tasks__organization=user.organization) |
                Q(tasks__organization__in=child_orgs)
            ).distinct()
        else:
            queryset = SocialMediaPost.objects.none()
        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start:
            queryset = queryset.filter(published_at__gte=start)
        if end:
            queryset = queryset.filter(published_at__lte=end)

        return queryset
    
    @action(detail=False, methods=['get'], url_path='meta')
    def get_meta(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "platforms": get_enum_choices(SocialMediaPost.Platform),
            "metrics": [
                {'value': 'comments', 'label': 'Comments'},
                {'value': 'likes', 'label': 'Likes'},
                {'value': 'views', 'label': 'Views'},
                {'value': 'reach', 'label': 'Reach'},
            ]
        })