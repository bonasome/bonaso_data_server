from django.shortcuts import render, redirect
from django.db.models import Q
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework import serializers
from rest_framework import status

from datetime import datetime, date

from projects.models import Project
from messaging.models import Message, Announcement
from messaging.serializers import MessageSerializer, AnnouncementSerializer
from django.contrib.auth import get_user_model
User = get_user_model()

class MessageViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['sent_on']
    search_fields = ['subject', 'body', 'sender__first_name', 'sender__last_name', 'recipient_links__recipient__first_name', 'recipient_links__recipient__last_name']

    def get_queryset(self):
        user = self.request.user
        queryset = Message.objects.filter(Q(recipients=user) | Q(sender=user)).distinct()
        return queryset

class AnnouncementViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AnnouncementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['sent_on']
    search_fields = ['subject', 'body', 'project__name', 'organization__name']

    def get_queryset(self):
        user = self.request.user
        queryset = Announcement.objects.filter(Q(organization=None) | Q(organization=user.organization) | Q(cascade_to_children=True, organization=user.organization.parent_organization) | Q(project__organizations=user.organization))
        return queryset