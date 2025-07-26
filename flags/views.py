from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.shortcuts import get_object_or_404
from django.forms.models import model_to_dict
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q, Prefetch
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework import status

from projects.models import ProjectOrganization
from flags.models import Flag
from flags.serializers import FlagSerializer

class FlagViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = FlagSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, OrderingFilter]
    ordering_fields = ['-created_at']
    search_fields = ['reason_type', 'reason']
    
    def get_queryset(self):
        user = self.request.user
        queryset = Flag.objects.all()
        if user.role in ['admin', 'client']:
            return queryset
        if user.role in ['meofficer', 'manager']:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            queryset = queryset.filter(
                Q(caused_by__organization=user.organization) | Q(caused_by__organization__in=child_orgs)
            )
            return queryset.filter()
        else:
            return queryset.filter(caused_by=user)
    @action(detail=True, methods=['patch'], url_path='raise-flag')
    def raise_flag(self, request, pk=None):
        user = request.user
        respondent = self.get_object()

        if user.role not in ['admin', 'meofficer', 'manager']:
            raise PermissionDenied('You do not have permission to raise a flag.')

        reason = request.data.get('reason')
        if not reason:
            return Response({"detail": "You must provide a reason for creating a flag."}, status=status.HTTP_400_BAD_REQUEST)

        flag = RespondentFlag.objects.create(
            respondent=respondent,
            created_by=user,
            reason=reason,
        )
        return Response({"detail": "Respondent flagged.", "flag": RespondentFlagSerializer(flag).data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='resolve-flag/(?P<respondentflag_id>[^/.]+)')
    def resolve_flag(self, request, pk=None, respondentflag_id=None):
        user = request.user
        respondent = self.get_object()

        if user.role not in ['admin', 'meofficer', 'manager']:
            return Response({"detail": "You do not have permission to resolve a flag for this post."}, status=status.HTTP_403_FORBIDDEN)

        respondent_flag = get_object_or_404(RespondentFlag, id=respondentflag_id, respondent=respondent)

        if respondent_flag.resolved:
            return Response({"detail": "This flag is already resolved."}, status=status.HTTP_400_BAD_REQUEST)

        resolved_reason = request.data.get('resolved_reason')
        if not resolved_reason:
            return Response({"detail": "You must provide a reason for resolving a flag."}, status=status.HTTP_400_BAD_REQUEST)

        respondent_flag.resolved = True
        respondent_flag.resolved_by = user
        respondent_flag.resolved_reason = resolved_reason
        respondent_flag.resolved_at = now()
        respondent_flag.save()

        return Response({"detail": "Flag resolved.", "flag": RespondentFlagSerializer(respondent_flag).data}, status=status.HTTP_200_OK)
    @action(detail=True, methods=['patch'], url_path='raise-flag')
    def raise_flag(self, request, pk=None):
        user = request.user
        interaction = self.get_object()
        if user.role not in ['admin', 'meofficer', 'manager']:
            raise PermissionDenied('You do not have permission to raise a flag.')
        if user.role in ['meofficer', 'manager'] and not (
            interaction.task.organization == user.organization or 
            ProjectOrganization.objects.filter(organization=interaction.task.organization, project=interaction.task.project, parent_organization=user.organization).exists()):
            raise PermissionDenied('You do not have permission to raise a flag for this interaction.')
        reason = request.data.get('reason', None)
        if not reason:
            return Response({"detail": f"You must provide a reason for creating a flag."}, status=status.HTTP_400_BAD_REQUEST)
        InteractionFlag.objects.create(
            interaction=interaction,
            created_by = user,
            reason=reason,
        )
        return Response({"detail": f"Interaction flagged."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=['patch'], url_path='resolve-flag/(?P<interactionflag_id>[^/.]+)')
    def resolve_flag(self, request, pk=None, interactionflag_id=None):
        user = request.user
        interaction = self.get_object()
        interaction_flag = InteractionFlag.objects.filter(id=interactionflag_id).first()

        if user.role not in ['admin', 'meofficer', 'manager']:
            return Response({"detail": f"You do not have permissiont to resolve a flag for this interaction."}, status=status.HTTP_403_FORBIDDEN)
        if user.role in ['meofficer', 'manager'] and not (
        interaction.task.organization == user.organization or 
         ProjectOrganization.objects.filter(organization=interaction.task.organization, project=interaction.task.project, parent_organization=user.organization).exists()):
            return Response({"detail": f"You do not have permissiont to resolve a flag for this interaction."}, status=status.HTTP_403_FORBIDDEN)

        if not interaction_flag:
            return Response({"detail": f"Flag not found."}, status=status.HTTP_400_BAD_REQUEST)
        
        resolved_reason = request.data.get('resolved_reason', None)
        if not resolved_reason:
            return Response({"detail": f"You must provide a reason for resolving a flag."}, status=status.HTTP_400_BAD_REQUEST)
        
        interaction_flag.resolved = True
        interaction_flag.resolved_by = user
        interaction_flag.resolved_reason=resolved_reason
        interaction_flag.resolved_at=now()
        interaction_flag.save()
        print(interaction_flag.resolved)
        return Response({"detail": f"Flag resolved."}, status=status.HTTP_200_OK)


    @action(detail=False, methods=['get'], url_path='flagged')
    def get_flagged(self, request):
        user = request.user
        role = user.role
        org = user.organization

        # Start with flagged interactions
        flags = InteractionFlag.objects.all()
        related_ids = [flag.interaction.id for flag in flags.all()]
        queryset = Interaction.objects.filter(id__in=related_ids)

        # Role-based filtering
        if role == 'client':
            raise PermissionDenied('You do not have permission to view this page.')
        elif role in ['meofficer', 'manager']:
            child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)

            queryset = queryset.filter(
                Q(task__organization=user.organization) | Q(task__organization__in=child_orgs)
            )
        elif role == 'data_collector':
            queryset = queryset.filter(created_by=user)

        project_id = request.query_params.get('project')
        organization_id = request.query_params.get('organization')
        indicator_id = request.query_params.get('indicator')
        resolved_param = request.query_params.get('resolved')
        auto_param = request.query_params.get('auto_flagged')
        start_param = self.request.query_params.get('start')
        if start_param:
            queryset = queryset.filter(interaction_date__gte=start_param)

        end_param = self.request.query_params.get('end')
        if end_param:
            queryset = queryset.filter(interaction_date__lte=end_param)

        if project_id:
            queryset = queryset.filter(task__project__id = project_id)
        if organization_id:
            queryset = queryset.filter(task__organization__id = organization_id)
        if indicator_id:
            queryset = queryset.filter(task__indicator__id = indicator_id)
        
        if resolved_param:
            queryset = queryset.filter(flags__resolved = resolved_param in ['true', '1']).distinct()
            print(queryset.count())
        if auto_param:
            queryset = queryset.filter(flags__auto_flagged = auto_param in ['true', '1']).distinct()
            print(queryset.count())

        # Search filter (e.g., by respondent name or ID or comment)
        search_term = request.query_params.get('search')
        if search_term:
            queryset = queryset.filter(
                Q(respondent__first_name__icontains=search_term) |
                Q(respondent__last_name__icontains=search_term) |
                Q(respondent__village__icontains=search_term) |
                Q(respondent__uuid__icontains=search_term) |
                Q(comments__icontains=search_term) |
                Q(task__indicator__name__icontains=search_term) |
                Q(task__indicator__code__icontains=search_term) |
                Q(task__organization__name__icontains=search_term) |
                Q(task__project__name__icontains=search_term) |
                Q(flags__reason__icontains=search_term)
            ).distinct()

        # Pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = InteractionSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        # No pagination fallback
        serializer = InteractionSerializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
    
    
    @action(detail=True, methods=['patch'], url_path='flag-count/(?P<count_id>[^/.]+)')
    def flag_count(self, request, pk=None, count_id=None):
        from events.serializers import CountFlagSerializer
        event=self.get_object()
        user=request.user
        reason = request.data.get('reason', None)
        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {'detail': 'You do not have permission to flag event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        count = DemographicCount.objects.filter(id=count_id).first()
        if not count:
            return Response(
                {'detail': 'Invalid count id provided.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if user.role != 'admin':
             if count.task.organization != user.organization and not ProjectOrganization.objects.filter(organization=count.task.organization, parent_organization=user.organization).exists():
                return Response(
                    {'detail': 'You do not have permission to flag counts for this event.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        if reason is None:
            return Response(
                {'detail': 'Missing flag reason.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        
        flag = CountFlag.objects.create(count=count, created_by=user, reason=reason)
        serializer = CountFlagSerializer(flag)
        return Response({"detail": f"Flagged count {count_id}.", "flag": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='resolve-flag/(?P<count_flags_id>[^/.]+)')
    def resolve_count(self, request, pk=None, count_flags_id=None):
        from events.serializers import CountFlagSerializer
        event=self.get_object()
        user=request.user
        reason = request.data.get('resolved_reason', None)
        if user.role not in ['meofficer', 'admin', 'manager']:
            return Response(
                {'detail': 'You do not have permission to flag event counts.'},
                status=status.HTTP_403_FORBIDDEN
            )
        flag = CountFlag.objects.filter(id=count_flags_id).first()
        if not flag:
            return Response(
                {'detail': 'Flag does not exist.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if user.role != 'admin':
            if flag.count.task.organization != user.organization and not ProjectOrganization.objects.filter(organization=flag.count.task.organization, parent_organization=user.organization).exists():
                return Response(
                    {'detail': 'You do not have permission to flag counts for this event.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        if reason is None:
            return Response(
                {'detail': 'Missing flag reason.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        flag.resolved = True
        flag.resolved_at = now()
        flag.resolved_by = user
        flag.resolved_reason = reason
        flag.save()
        serializer = CountFlagSerializer(flag)
        return Response({"detail": f"Resolved flag.", "flag": serializer.data}, status=status.HTTP_200_OK)