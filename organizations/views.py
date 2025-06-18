from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from django.db.models import Case, When, Value, IntegerField
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics
from rest_framework.decorators import action
from django.db.models import Q
from users.restrictviewset import RoleRestrictedViewSet
from organizations.models import Organization
from projects.models import Project
from organizations.serializers import OrganizationListSerializer, OrganizationSerializer


class OrganizationViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    queryset = Organization.objects.none()
    serializer_class = OrganizationSerializer
    filter_backends = [SearchFilter, OrderingFilter]
    filterset_fields = ['project', 'parent_organization']
    ordering_fields = ['name']
    search_fields = ['name'] 
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)
        if role == 'admin':
            queryset = Organization.objects.all()
        elif role and org:
            queryset =  Organization.objects.filter(Q(parent_organization=org) | Q(id=org.id))
        else:
            return Organization.objects.none()
        parent_organization = self.request.query_params.get('parent_organization')
        if parent_organization:
            queryset = queryset.filter(Q(parent_organization=org) | Q(id=org.id)).annotate(priority=Case(
                   When(pk=parent_organization, then=Value(0)),
                   default=Value(1),
                   output_field=IntegerField(),
               )
           ).order_by('priority', 'name')
            
        project_id = self.request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(projectorganization__project__id=project_id)
        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return OrganizationListSerializer
        else:
            return OrganizationSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user) 
    