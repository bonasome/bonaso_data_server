from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from rest_framework import status

from django.apps import apps
from django.db.models import Q
from django.contrib.contenttypes.models import ContentType
from django.utils.timezone import now
from users.restrictviewset import RoleRestrictedViewSet

from projects.models import ProjectOrganization
from flags.models import Flag
from flags.serializers import FlagSerializer
from respondents.utils import get_enum_choices

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
            obj=queryset.first()
            print(obj.caused_by.organization)
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
    @action(detail=False, methods=['get'], url_path='meta')
    def get_meta(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "flag_reasons": get_enum_choices(Flag.FlagReason),
        })
    
    @action(detail=False, methods=['post'], url_path='raise-flag')
    def raise_flag(self, request):
        ALLOWED_FLAG_MODELS = {
            "respondents.respondent",
            "respondents.interaction",
            "events.demographiccount",
            "social.socialmediapost"
        }
        user = request.user

        if user.role not in ['admin', 'meofficer', 'manager']:
            raise PermissionDenied('You do not have permission to raise a flag.')
        
        model_str = request.data.get('model')
        obj_id = request.data.get('id')

        if not model_str or not obj_id:
            return Response({"detail": "Model and ID are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        if model_str.lower() not in ALLOWED_FLAG_MODELS:
            return Response({"detail": "Model not allowed for flagging."}, status=400)
        
        try:
            app_label, model_name = model_str.lower().split('.')
            model = apps.get_model(app_label, model_name)
            if not model:
                raise LookupError
        except (ValueError, LookupError):
            return Response({"detail": f'"{model_str}" is not a valid model.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_obj = model.objects.get(pk=obj_id)
        except model.DoesNotExist:
            return Response({"detail": f"No {model.__name__} with id {obj_id}."}, status=status.HTTP_404_NOT_FOUND)

        if user.role != 'admin':
            try:
                org = getattr(target_obj.created_by, 'organization', None)
                if org != user.organization and not ProjectOrganization.objects.filter(parent_organization=user.organization, organization=org).exists():
                    return Response({"detail": "You do not have permission to create a flag for this object."}, status=status.HTTP_403_FORBIDDEN)
            except:
                return Response({"detail": "You do not have permission to create a flag for this object."}, status=status.HTTP_403_FORBIDDEN)
        reason_type = request.data.get('reason_type')
        reason = request.data.get('reason')
        if not reason or not reason_type:
            return Response({"detail": "You must provide a reason for creating a flag."}, status=status.HTTP_400_BAD_REQUEST)

        flag = Flag.objects.create(
            content_type=ContentType.objects.get_for_model(model),
            object_id=target_obj.id,
            created_by=user,
            caused_by=user,
            reason=reason,
            reason_type=reason_type,
        )

        return Response({"detail": f"{model.__name__} flagged.", "flag": FlagSerializer(flag).data}, 
                status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='resolve-flag')
    def resolve_flag(self, request, pk=None):
        user = request.user
        flag = self.get_object()

        if user.role not in ['admin', 'meofficer', 'manager']:
            return Response({"detail": "You do not have permission to resolve a flag."}, status=status.HTTP_403_FORBIDDEN)

        if user.role != 'admin':
            if flag.caused_by.organization != user.organization and not ProjectOrganization.objects.filter(parent_organization=user.organization, organization=flag.caused_by.organization).exists():
                return Response({"detail": "You do not have permission to resolve a flag for this object."}, status=status.HTTP_403_FORBIDDEN)

        if flag.resolved:
            return Response({"detail": "This flag is already resolved."}, status=status.HTTP_400_BAD_REQUEST)

        resolved_reason = request.data.get('resolved_reason')
        if not resolved_reason:
            return Response({"detail": "You must provide a reason for resolving a flag."}, status=status.HTTP_400_BAD_REQUEST)

        flag.resolved = True
        flag.resolved_by = user
        flag.resolved_reason = resolved_reason
        flag.resolved_at = now()
        flag.save()

        return Response({"detail": "Flag resolved.", "flag": FlagSerializer(flag).data}, status=status.HTTP_200_OK)
    