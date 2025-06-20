from django.shortcuts import render
from rest_framework import viewsets, permissions
from uploads.models import NarrativeReport
from uploads.serializers import NarrativeReportSerializer
from organizations.models import Organization
from django.db.models import Q
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status

class NarrativeReportViewSet(viewsets.ModelViewSet):
    queryset = NarrativeReport.objects.all().order_by('-created_at')
    serializer_class = NarrativeReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['organization', 'project', 'created_at']
    ordering_fields = ['created_at']
    search_fields = ['organization__name', 'project__name', 'title', 'description']  # <-- fixed missing comma + added nested lookups

    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return NarrativeReport.objects.all()
        elif user.role in ['meofficer', 'manager']:
            return NarrativeReport.objects.filter(
                Q(organization=user.organization) |
                Q(organization__parent_organization=user.organization)
            )
        else:
            return NarrativeReport.objects.none()

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        user = request.user
        instance = self.get_object()

        if user.role not in ['meofficer', 'manager', 'admin']:
            return Response(
                {"detail": "You do not have permission to download reports."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Restrict non-admins to their own or child orgs
        if user.role != 'admin':
            org = instance.organization
            if not (
                org and (
                    org.id == user.organization_id or
                    (org.parent_organization_id == user.organization_id)
                )
            ):
                return Response(
                    {"detail": "You do not have permission to download this report."},
                    status=status.HTTP_403_FORBIDDEN
                )

        if not instance.file:
            return Response({"detail": "File not found."}, status=status.HTTP_404_NOT_FOUND)

        return FileResponse(
            instance.file.open(),
            as_attachment=True,
            filename=instance.file.name.split('/')[-1]
        )