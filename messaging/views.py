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
from django.utils.timezone import now
from datetime import datetime, date

from projects.models import Project
from projects.utils import get_valid_orgs, is_child_of
from profiles.serializers import ProfileListSerailizer
from messaging.models import Message, Announcement, MessageRecipient, Alert, AlertRecipient
from messaging.serializers import MessageSerializer, AnnouncementSerializer, AlertSerializer
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
        if self.action in ['update', 'partial_update', 'set_completed']:
            queryset = Message.objects.filter(Q(sender=user) | Q(recipients=user))
        else:
            queryset = Message.objects.filter(Q(recipients=user) | Q(sender=user)).distinct().exclude(deleted_by_sender=True)
            queryset = queryset.filter(parent__isnull=True)
        return queryset
    
    @action(detail=False, methods=['get'], url_path='recipients')
    def get_recipients(self, request, pk=None):
        user = request.user
        queryset = User.objects.all()
        if user.role in ['meofficer', 'manager']:
            valid_orgs = get_valid_orgs(user)
            queryset = queryset.filter(Q(organization_id__in=valid_orgs) | Q(role='admin'))
        elif user.role in ['data_collector', 'client']:
            queryset = queryset.filter(Q(organization=user.organization)|Q(role='admin'))
        serializer = ProfileListSerailizer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['patch'], url_path='read')
    def set_read(self, request, pk=None):
        user = request.user
        message = self.get_object()
        mr = MessageRecipient.objects.filter(Q(message=message, recipient=user) | Q(message__parent=message, recipient=user))
        mr.update(read=True, read_on=now())
        return Response(
                {'detail': 'Message read.'},
                status=status.HTTP_200_OK
            )
    @action(detail=True, methods=['patch'], url_path='complete')
    def set_completed(self, request, pk=None):
        user = request.user
        message = self.get_object()
        mr = MessageRecipient.objects.filter(recipient=user, message=message)
        mr.update(completed=True, completed_on=now())
        return Response(
                {'detail': 'Message completed.'},
                status=status.HTTP_200_OK
            )
    

class AnnouncementViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AnnouncementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['sent_on']
    search_fields = ['subject', 'body', 'project__name', 'organization__name']

    def get_queryset(self):
        user = self.request.user
        
        queryset = Announcement.objects.filter(Q(organization=None) | Q(organization=user.organization) | 
            Q(project__organizations=user.organization))
        return queryset

class AlertViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AlertSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['sent_on']

    def get_queryset(self):
        user = self.request.user
        queryset = Alert.objects.filter(recipients=user)
        return queryset

    @action(detail=True, methods=['patch'], url_path='read')
    def set_read(self, request, pk=None):
        user = request.user
        alert = self.get_object()
        ar = AlertRecipient.objects.filter(alert=alert, recipient=user)
        ar.update(read=True, read_on=now())
        return Response(
                {'detail': 'Alert read.'},
                status=status.HTTP_200_OK
            )