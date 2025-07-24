from django.shortcuts import render, redirect
from django.forms.models import model_to_dict
from rest_framework.viewsets import ModelViewSet
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework.decorators import action
from social.models import SocialMediaPost, SocialMediaPostFlag
from social.serializers import SocialMediaPostSerializer
from projects.models import ProjectOrganization
from social.utils import user_has_post_access
from rest_framework import status
from django.utils.timezone import now
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

        if user.role in ['admin', 'client']:
            return SocialMediaPost.objects.all()

        if user.role in ['meofficer', 'manager']:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            return SocialMediaPost.objects.filter(
                Q(task__organization=user.organization) |
                Q(task__organization__in=child_orgs)
            )

        return SocialMediaPost.objects.none()
    

    @action(detail=False, methods=['get'], url_path='get-meta')
    def get_meta(self, request):
        platforms = [p for p, _ in SocialMediaPost.Platform.choices]
        platform_labels = [p.label for p in SocialMediaPost.Platform]
        return Response({
            'platforms': platforms,
            'platform_labels': platform_labels,
        })

    @action(detail=True, methods=['patch'], url_path='raise-flag')
    def raise_flag(self, request, pk=None):
        user = request.user
        post = self.get_object()

        if user.role not in ['admin', 'meofficer', 'manager']:
            raise PermissionDenied('You do not have permission to raise a flag.')

        if user.role in ['meofficer', 'manager'] and not user_has_post_access(user, post):
            raise PermissionDenied('You do not have permission to raise a flag for this post.')

        reason = request.data.get('reason')
        if not reason:
            return Response({"detail": "You must provide a reason for creating a flag."}, status=status.HTTP_400_BAD_REQUEST)

        SocialMediaPostFlag.objects.create(
            social_media_post=post,
            created_by=user,
            reason=reason,
        )
        return Response({"detail": "Post flagged."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='resolve-flag/(?P<postflag_id>[^/.]+)')
    def resolve_flag(self, request, pk=None, postflag_id=None):
        user = request.user
        post = self.get_object()

        if user.role not in ['admin', 'meofficer', 'manager']:
            return Response({"detail": "You do not have permission to resolve a flag for this post."}, status=status.HTTP_403_FORBIDDEN)

        if user.role in ['meofficer', 'manager'] and not user_has_post_access(user, post):
            return Response({"detail": "You do not have permission to resolve a flag for this post."}, status=status.HTTP_403_FORBIDDEN)

        post_flag = get_object_or_404(SocialMediaPostFlag, id=postflag_id, social_media_post=post)

        if post_flag.resolved:
            return Response({"detail": "This flag is already resolved."}, status=status.HTTP_400_BAD_REQUEST)

        resolved_reason = request.data.get('resolved_reason')
        if not resolved_reason:
            return Response({"detail": "You must provide a reason for resolving a flag."}, status=status.HTTP_400_BAD_REQUEST)

        post_flag.resolved = True
        post_flag.resolved_by = user
        post_flag.resolved_reason = resolved_reason
        post_flag.resolved_at = now()
        post_flag.save()

        return Response({"detail": "Flag resolved."}, status=status.HTTP_200_OK)