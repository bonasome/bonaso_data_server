from rest_framework.viewsets import ModelViewSet
from rest_framework.exceptions import PermissionDenied

class RoleRestrictedViewSet(ModelViewSet):
    '''
    Prevent users with no organization/client_organization and no role from accessing viewsets. 
    '''
    restricted_roles = ['view_only']

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) in self.restricted_roles:
            return self.queryset.none()
        if getattr(user, 'organization', None) is None and getattr(user, 'client_organization', None) is None:
            return self.queryset.none()
        return super().get_queryset()

    def check_permissions(self, request):
        super().check_permissions(request)
        user = self.request.user
        if getattr(request.user, 'role', None) in self.restricted_roles:
            raise PermissionDenied("Your role does not have permission to access this resource.")
        if getattr(user, 'organization', None) is None and getattr(user, 'client_organization', None) is None:
            raise PermissionDenied("You must be a member of an organization to access this resource.")