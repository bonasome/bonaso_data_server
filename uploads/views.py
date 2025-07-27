from django.shortcuts import render
from rest_framework import viewsets, permissions
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status


from uploads.models import NarrativeReport
from uploads.serializers import NarrativeReportSerializer
from projects.models import ProjectOrganization

from django.db.models import Q



class NarrativeReportViewSet(viewsets.ModelViewSet):
    queryset = NarrativeReport.objects.all().order_by('-created_at')
    serializer_class = NarrativeReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['organization', 'project', 'created_at']
    ordering_fields = ['created_at']
    search_fields = ['organization__name', 'project__name', 'title', 'description']  # <-- fixed missing comma + added nested lookups

    def get_queryset(self):
        '''
        Admins see all, clients related projects, higher roles see their org and child orgs.
        '''
        user = self.request.user
        if user.role == 'admin':
            return NarrativeReport.objects.all()
        if user.role == 'client':
            return NarrativeReport.objects.filter(project__client=user.client_organization)
        elif user.role in ['meofficer', 'manager']:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
            return NarrativeReport.objects.filter(Q(organization=user.organization) | Q(organization__in=child_orgs))
        else:
            return NarrativeReport.objects.none()
    
    def perform_create(self, serializer):
        '''
        Save with uploaded by.
        '''
        user = self.request.user
        serializer.save(uploaded_by=user)

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        '''
        Special action to collect and download a report if they are an admin, the report is theirs or their
        child orgs, or they are a client and the report is in their project.
        '''
        user = request.user
        instance = self.get_object()

        if user.role not in ['meofficer', 'manager', 'admin']:
            return Response(
                {"detail": "You do not have permission to download reports."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Restrict non-admins to their own or child orgs
        if user.role not in  ['admin', 'client']:
            if not ( instance.organization == user.organization or 
            ProjectOrganization.objects.filter(organization=instance.organization, project=instance.project, parent_organization=user.organization).exists()):
                return Response(
                    {"detail": "You do not have permission to download this report."},
                    status=status.HTTP_403_FORBIDDEN
                )
        if user.role == 'client' and not instance.project.client == user.client_organization:
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