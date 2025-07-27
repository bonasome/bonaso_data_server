from rest_framework.permissions import BasePermission

class IsActiveUser(BasePermission):
    '''
    Do not allow inactive users to be authenticated.
    '''
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_active