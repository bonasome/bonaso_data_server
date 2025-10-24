from django.shortcuts import render, redirect
from django.db.models import Q, Exists, OuterRef

from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status

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
            base_q = Q(organization=user.organization)

            # Child-host relationships (parent-child link within a project)
            project_child_rels = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            )

            # Events where a child org hosts but project comes via tasks
            child_host_task_q = Q(
                Exists(
                    project_child_rels.filter(
                        organization=OuterRef('organization'),
                        project=OuterRef('tasks__project')
                    )
                )
            )
            queryset = SocialMediaPost.objects.filter(
                base_q | child_host_task_q
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
    
    @action(detail=True, methods=['patch'], url_path='update-metrics')
    def update_metrics(self, request, pk=None):
        post = self.get_object()
        user=request.user
        # metrics: { likes: 10, comments: 4 }
        metrics = request.data.get('metrics', {})
        ALLOWED_METRICS = {'likes', 'comments', 'views', 'reach'}
        invalid = set(metrics.keys()) - ALLOWED_METRICS
        if invalid:
            return Response(
                {"detail": f"Invalid metric fields: {', '.join(invalid)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if user.role != 'admin':
            if user.organization != post.organization:
                pids = [t.project_id for t in post.tasks.all()]
                if not ProjectOrganization.objects.filter(project__in=pids, parent_organization=user.organization, organization=post.organization).exists():
                    return Response({"detail": "You cannot edit metrics for this post."}, status.HTTP_403_FORBIDDEN)
        for metric, value in metrics.items():
            try:
                value = int(value)
            except (TypeError, ValueError):
                return Response(
                    {"detail": f"Metric '{metric}' must be a number."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            setattr(post, metric, value)
        post.save()
        
        return Response({'detail': 'Metrics successfully updated!'}, status.HTTP_200_OK)


        
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