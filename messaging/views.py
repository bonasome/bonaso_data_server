from django.shortcuts import render, redirect
from django.db.models import Q
from django.utils.timezone import now

from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from rest_framework import status

from django.contrib.auth import get_user_model

User = get_user_model()

from users.restrictviewset import RoleRestrictedViewSet

from profiles.serializers import ProfileListSerializer
from projects.models import Project, ProjectOrganization
from messaging.models import Message, Announcement, MessageRecipient, Alert, AlertRecipient, AnnouncementRecipient
from messaging.serializers import MessageSerializer, AnnouncementSerializer, AlertSerializer


class MessageViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['sent_on']
    search_fields = ['subject', 'body', 'sender__first_name', 'sender__last_name', 'recipient_links__recipient__first_name', 'recipient_links__recipient__last_name']

    def get_queryset(self):
        '''
        Only see messages you are a sender of or recipient of. Replies should be nested by default, but 
        editable.
        '''
        user = self.request.user
        if self.action in ['update', 'partial_update', 'set_completed']:
            queryset = Message.objects.filter(Q(sender=user) | Q(recipients=user)).distinct()
        else:
            #by default, exclude "replies" (with parent) from the queryset, since we prefer to work with these as nested data
            queryset = Message.objects.filter(Q(recipients=user) | Q(sender=user)).distinct().exclude(deleted_by_sender=True)
            queryset = queryset.filter(parent__isnull=True)
        return queryset
    
    @action(detail=False, methods=['get'], url_path='recipients')
    def get_recipients(self, request):
        '''
        Get a list of valid profile recipients. Ideally only admins and people within your organization.
        '''
        user = request.user
        if user.role == 'admin':
            queryset = User.objects.all()

        elif user.role in ['meofficer', 'manager']:
            org_ids = [user.organization_id]
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization_id', flat=True)
            org_ids += list(child_orgs)
            queryset = User.objects.filter(Q(organization_id__in=org_ids)| Q(role='admin'))

        elif user.role == 'client':
            queryset = User.objects.filter(Q(client_organization=user.client_organization) | Q(role='admin'))

        else:
            queryset = User.objects.filter(Q(organization__id=user.organization.id) | Q(role='admin') )

        search_term = request.query_params.get('search')
        if search_term:
            queryset = queryset.filter(
                Q(first_name__icontains=search_term) |
                Q(last_name__icontains=search_term) |
                Q(username__icontains=search_term)
            )

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = ProfileListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = ProfileListSerializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['patch'], url_path='read')
    def set_read(self, request, pk=None):
        '''
        Simple ping action to mark a message as read when opened.
        '''
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
        '''
        Simple ping action to mark a message as completed when a button is clicked.
        '''
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
    filterset_fields = ['project']
    ordering_fields = ['sent_on']
    search_fields = ['subject', 'body', 'project__name', 'organizations__name']

    def get_queryset(self):
        user = self.request.user
        valid_ps = Project.objects.filter(organizations=user.organization, status=Project.Status.ACTIVE)
        if user.role == 'admin':
            return Announcement.objects.all()
        if user.role == 'client':
            return Announcement.objects.filter(Q(visible_to_all=True) | Q(project__client=user.client_organization))
        if user.role in ['meofficer', 'manager']:
            child_org_links = ProjectOrganization.objects.filter(parent_organization=user.organization)
            child_orgs = [co.organization for co in child_org_links]
            queryset = Announcement.objects.filter(
                Q(visible_to_all=True, project=None) |  # Public & not project-specific
                Q(organizations=user.organization) |     # Org-specific
                Q(organizations__in=child_orgs) | #parent orgs can see children
                Q(project__in=valid_ps, visible_to_all=True)  # Project-specific & public
            )
            return queryset
        else:
            queryset = Announcement.objects.filter(
                Q(visible_to_all=True, project=None) |  # Public & not project-specific
                Q(organizations=user.organization)     # Org-specific
            )
            return queryset
    @action(detail=True, methods=['patch'], url_path='read')
    def set_read(self, request, pk=None):
        '''
        Ping to mark as read when opened on the frontend.
        '''
        user = request.user
        annc = self.get_object()
        if AnnouncementRecipient.objects.filter(announcement=annc, recipient=user).exists():
            return Response(
                {'detail': 'Announcement already read.'},
                status=status.HTTP_200_OK
            )

        recipient = AnnouncementRecipient.objects.create(announcement=annc, recipient=user)
        return Response(
            {'detail': 'Announcement read.', 'read_at': recipient.read_at},
            status=status.HTTP_200_OK
        )

class AlertViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = AlertSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['sent_on']

    def get_queryset(self):
        '''
        Only get your alerts.
        '''
        user = self.request.user
        queryset = Alert.objects.filter(recipients=user)
        return queryset

    @action(detail=True, methods=['patch'], url_path='read')
    def set_read(self, request, pk=None):
        '''
        Ping to mark as read when opened on the frontend.
        '''
        user = request.user
        alert = self.get_object()
        ar = AlertRecipient.objects.filter(alert=alert, recipient=user)
        ar.update(read=True, read_on=now())
        return Response(
                {'detail': 'Alert read.'},
                status=status.HTTP_200_OK
            )