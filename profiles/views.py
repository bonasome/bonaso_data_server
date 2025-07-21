from django.shortcuts import render
from users.restrictviewset import RoleRestrictedViewSet
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from profiles.models import FavoriteProject, FavoriteRespondent, FavoriteEvent
from profiles.serializers import ProfileSerializer, FavoriteProjectSerializer, FavoriteRespondentSerializer, FavoriteEventSerializer
from django.contrib.auth import get_user_model
from rest_framework import status
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.decorators import action

from respondents.models import Interaction, Respondent
from organizations.models import Organization
from indicators.models import Indicator
from projects.models import Project, Task, Target
from projects.utils import get_valid_orgs
from uploads.models import NarrativeReport
from django.utils import timezone
from datetime import datetime, timedelta
from respondents.serializers import SimpleInteractionSerializer

User = get_user_model()


class ProfileViewSet(RoleRestrictedViewSet):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['organization', 'role', 'is_active', 'client_organization']
    ordering_fields = ['last_name']
    search_fields = ['last_name','first_name', 'username']

    @action(detail=False, methods=['get'], url_path='activity/(?P<user_id>[^/.]+)/feed')
    def feed_data(self, request, user_id):
        requesting_user = self.request.user
        profile_user = get_object_or_404(User, id=user_id)

        # Check permission before querying
        if requesting_user.role != 'admin':
            if requesting_user.role not in ['meofficer', 'manager'] or not (
                profile_user.organization == requesting_user.organization or
                getattr(profile_user.organization, 'parent_organization', None) == requesting_user.organization
            ):
                if requesting_user.id != profile_user.id:
                    return Response(None, status=403)
        search_term = request.query_params.get('search', '').lower()

        interactions = Interaction.objects.filter(Q(created_by=profile_user) | Q(updated_by=profile_user))
        respondents = Respondent.objects.filter(Q(created_by=profile_user) | Q(updated_by=profile_user))
        indicators = Indicator.objects.filter(Q(created_by=profile_user) | Q(updated_by=profile_user))
        organizations = Organization.objects.filter(Q(created_by=profile_user) | Q(updated_by=profile_user))
        projects = Project.objects.filter(Q(created_by=profile_user) | Q(updated_by=profile_user))
        tasks = Task.objects.filter(created_by=profile_user)
        targets = Target.objects.filter(Q(created_by=profile_user) | Q(updated_by=profile_user))
        nr = NarrativeReport.objects.filter(uploaded_by = profile_user)
        feed = []
        for ir in interactions:
            r_label = (f'{ir.respondent.first_name} {ir.respondent.last_name}') if not ir.respondent.is_anonymous else f'Anonymous respondent {ir.respondent.uuid}'
            if ir.created_by == profile_user:
                feed.append({
                    "type": "interaction",
                    "id": ir.id,
                    "respondent": ir.respondent.id,
                    "date": ir.created_at,
                    "action": "created",
                    "summary": f"Created interaction for {ir.task.indicator.code} with {r_label}",
                })
            if hasattr(ir, "updated_by") and ir.updated_by == profile_user:
                feed.append({
                    "type": "interaction",
                    "id": ir.id,
                    "date": ir.updated_at,
                    "action": "updated",
                    "summary": f"Updated interaction for {ir.task.indicator.code} with {r_label}",
                })

        for r in respondents:
            r_label = (f'{r.first_name} {r.last_name}') if not r.is_anonymous else f'Anonymous respondent {r.uuid}'
            if r.created_by == profile_user:
                feed.append({
                    "type": "respondent",
                    "id": r.id,
                    "date": r.created_at,
                    "action": "created",
                    "summary": f"Created respondent {r_label}",
                })
            if hasattr(r, "updated_by") and r.updated_by == profile_user:
                feed.append({
                    "type": "respondent",
                    "id": r.id,
                    "date": r.updated_at,
                    "action": "updated",
                    "summary": f"Updated respondent {r_label}",
                })
        
        for ind in indicators:
            if ind.created_by == profile_user:
                feed.append({
                    "type": "indicator",
                    "id": ind.id,
                    "date": ind.created_at,
                    "action": "created",
                    "summary": f"Created indicator {ind.code}",
                })
            if hasattr(ind, "updated_by") and ind.updated_by == profile_user:
                feed.append({
                    "type": "indicator",
                    "id": ind.id,
                    "date": ind.updated_at,
                    "action": "updated",
                    "summary": f"Updated indicator {ind.code}",
                })
        
        for org in organizations:
            if org.created_by == profile_user:
                feed.append({
                    "type": "organization",
                    "id": org.id,
                    "date": org.created_at,
                    "action": "created",
                    "summary": f"Created organization {org.name}",
                })
            if hasattr(org, "updated_by") and org.updated_by == profile_user:
                feed.append({
                    "type": "organization",
                    "id": org.id,
                    "date": org.updated_at,
                    "action": "created",
                    "summary": f"Updated organization {org.name}",
                })
        for project in projects:
            if project.created_by == profile_user:
                feed.append({
                    "type": "project",
                    "id": project.id,
                    "date": project.created_at,
                    "action": "created",
                    "summary": f"Created project {project.name}",
                })
            if hasattr(project, "updated_by") and project.updated_by == profile_user:
                feed.append({
                    "type": "project",
                    "id": project.id,
                    "date": project.updated_at,
                    "action": "updated",
                    "summary": f"Updated project {project.name}",
                })
        for task in tasks:
            feed.append({
                "type": "task",
                "id": task.id,
                "action": "created",
                "project": task.project.id,
                "date": task.created_at,
                "action": "created",
                "summary": f"Created task {task.indicator.name} for {task.organization.name}",
            })
            
        for target in targets:
            if target.created_by == profile_user:
                feed.append({
                    "type": "target",
                    "id": target.id,
                    "date": target.created_at,
                    "project": target.task.project.id,
                    "action": "created",
                    "summary": f"Created target {target.task.indicator.name} for {target.task.organization.name}",
                })
            if hasattr(target, "updated_by") and target.updated_by == profile_user:
                feed.append({
                    "type": "target",
                    "id": target.id,
                    "date": target.updated_at,
                    "project": target.task.project.id,
                    "action": "updated",
                    "summary": f"Updated target {target.task.indicator.name} for {target.task.organization.name}",
                })
        for r in nr:
            feed.append({
                "type": "narrative_report",
                "id": r.id,
                "action": "created",
                "project": r.project.id,
                "date": r.created_at,
                "action": "created",
                "summary": f"Uploaded report {r.title}",
            })
        # Sort descending by date
        feed.sort(key=lambda x: x['date'], reverse=True)
        if search_term:
            feed = [
                item for item in feed
                if search_term in item.get('summary', '').lower()
                or search_term in item.get('type', '').lower()
            ]

        page = self.paginate_queryset(feed)
        if page is not None:
            return self.get_paginated_response(page)
        return Response(feed)


    @action(detail=False, methods=['get'], url_path='activity/(?P<user_id>[^/.]+)/chart')
    def chart_data(self, request, user_id):
        requesting_user = self.request.user
        profile_user = get_object_or_404(User, id=user_id)

        # Check permission before querying
        if requesting_user.role != 'admin':
            if requesting_user.role not in ['meofficer', 'manager'] or not (
                profile_user.organization == requesting_user.organization or
                getattr(profile_user.organization, 'parent_organization', None) == requesting_user.organization
            ):
                if requesting_user.id != profile_user.id:
                    return Response(None, status=403)

        one_year_ago = timezone.now() - timedelta(days=365)
        queryset = Interaction.objects.filter(
            created_by=user_id,
            created_at__gte=one_year_ago
        )

        serializer = SimpleInteractionSerializer(queryset, many=True)
        return Response(serializer.data)

    def paginate_queryset(self, queryset):
        # Disable pagination only for this specific action
        if self.action == 'chart_data':
            return None
        return super().paginate_queryset(queryset)
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'admin':
            return User.objects.all()
        elif user.role in ['meofficer', 'manager']:
            valid_orgs = get_valid_orgs(user)
            return User.objects.filter(organization_id__in=valid_orgs)
        
        return User.objects.filter(id=user.id)
    
    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Deleting users is not allowed. Mark them as inactive instead."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    @action(detail=False, methods=['get'], url_path='meta')
    def filter_options(self, request):
        roles = [r for r, _ in User.Role.choices]
        role_labels = [d.label for d in User.Role]
        return Response({
            'roles': roles,
            'role_labels': role_labels,
        })

    @action(detail=True, methods=['get'], url_path='favorites')
    def get_favorites(self, request, pk=None):
        user = request.user
        events = FavoriteEvent.objects.filter(user=user)
        projects = FavoriteProject.objects.filter(user=user)
        respondents = FavoriteRespondent.objects.filter(user=user)

        data = {
            'projects': FavoriteProjectSerializer(projects, many=True).data,
            'events': FavoriteEventSerializer(events, many=True).data,
            'respondents': FavoriteRespondentSerializer(respondents, many=True).data,
        }

        return Response(data, status=status.HTTP_200_OK)


class FavoriteEventViewSet(RoleRestrictedViewSet):
    serializer_class = FavoriteEventSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteEvent.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='is-favorited')
    def is_favorited(self, request):
        user = request.user
        event_id = request.query_params.get('id')
        if not event_id:
            return Response({"detail": "Missing id"}, status=400)

        is_fav = FavoriteEvent.objects.filter(user=user, event_id=event_id).exists()
        return Response({"is_favorited": is_fav})
    
    @action(detail=False, methods=['post'], url_path='unfavorite')
    def unfavorite(self, request):
        user = request.user
        event_id = request.data.get('event_id')
        if not event_id:
            return Response(
                {"detail": "No target object provided."},
                status=status.HTTP_400_BAD_REQUEST
            )
        fav = FavoriteEvent.objects.filter(user=user, event__id=event_id)
        if not fav.exists():
            return Response(
                {"detail": "No favorite found to unfavorite."},
                status=status.HTTP_400_BAD_REQUEST
            )
        fav.delete()
        return Response(
            {"detail": f"Event id {event_id} unfavorited."},
            status=status.HTTP_204_NO_CONTENT
        )

class FavoriteProjectViewSet(RoleRestrictedViewSet):
    serializer_class = FavoriteProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteProject.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='is-favorited')
    def is_favorited(self, request):
        user = request.user
        project_id = request.query_params.get('id')
        if not project_id:
            return Response({"detail": "Missing id"}, status=400)

        is_fav = FavoriteProject.objects.filter(user=user, project_id=project_id).exists()
        return Response({"is_favorited": is_fav})

    @action(detail=False, methods=['post'], url_path='unfavorite')
    def unfavorite(self, request):
        user = request.user
        project_id = request.data.get('project_id')
        if not project_id:
            return Response(
                {"detail": "No target object provided."},
                status=status.HTTP_400_BAD_REQUEST
            )
        fav = FavoriteProject.objects.filter(user=user, project__id=project_id)
        if not fav.exists():
            return Response(
                {"detail": "No favorite found to unfavorite."},
                status=status.HTTP_400_BAD_REQUEST
            )
        fav.delete()
        return Response(
            {"detail": f"Event id {project_id} unfavorited."},
            status=status.HTTP_204_NO_CONTENT
        )
    
class FavoriteRespondentViewSet(RoleRestrictedViewSet):
    serializer_class = FavoriteRespondentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FavoriteRespondent.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'], url_path='is-favorited')
    def is_favorited(self, request):
        user = request.user
        respondent_id = request.query_params.get('id')
        if not respondent_id:
            return Response({"detail": "Missing id"}, status=400)

        is_fav = FavoriteRespondent.objects.filter(user=user, respondent_id=respondent_id).exists()
        return Response({"is_favorited": is_fav})
    
    @action(detail=False, methods=['post'], url_path='unfavorite')
    def unfavorite(self, request):
        user = request.user
        respondent_id = request.data.get('respondent_id')
        if not respondent_id:
            return Response(
                {"detail": "No target object provided."},
                status=status.HTTP_400_BAD_REQUEST
            )
        fav = FavoriteRespondent.objects.filter(user=user, respondent__id=respondent_id)
        if not fav.exists():
            return Response(
                {"detail": "No favorite found to unfavorite."},
                status=status.HTTP_400_BAD_REQUEST
            )
        fav.delete()
        return Response(
            {"detail": f"Event id {respondent_id} unfavorited."},
            status=status.HTTP_204_NO_CONTENT
        )
