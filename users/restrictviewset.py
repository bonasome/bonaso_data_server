from rest_framework.viewsets import ModelViewSet
from rest_framework.exceptions import PermissionDenied

class RoleRestrictedViewSet(ModelViewSet):
    restricted_roles = ['view_only']  # or roles with limited access

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) in self.restricted_roles:
            return self.queryset.none()
        return super().get_queryset()