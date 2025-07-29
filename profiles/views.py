from django.shortcuts import render
from django.contrib.contenttypes.models import ContentType

from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter

from users.restrictviewset import RoleRestrictedViewSet
from django.contrib.auth import get_user_model
User = get_user_model()

from profiles.models import FavoriteObject
from profiles.serializers import ProfileSerializer, FavoriteObjectSerializer
from django.contrib.contenttypes.models import ContentType
from profiles.utils import get_favorited_object, get_user_activity
from respondents.utils import get_enum_choices
from projects.utils import get_valid_orgs




class ProfileViewSet(RoleRestrictedViewSet):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['organization', 'role', 'is_active', 'client_organization']
    ordering_fields = ['last_name']
    search_fields = ['last_name','first_name', 'username']

    def get_queryset(self):
        '''
        View only self +child orgs if higher role, self if lower role, and everyone if admin.
        '''
        user = self.request.user
        if user.role == 'admin':
            return User.objects.all()
        
        elif user.role in ['meofficer', 'manager']:
            valid_orgs = get_valid_orgs(user)
            return User.objects.filter(organization_id__in=valid_orgs)
        
        return User.objects.filter(id=user.id)
    
    @action(detail=True, methods=['get'], url_path='activity')
    def activity(self, request, pk=None):
        '''
        Get log of what objects a user has updated/created
        '''
        user = self.get_object()
        activity = get_user_activity(user)

        response_data = {}
        for model_label, instances in activity.items():
            response_data[model_label] = [str(instance) for instance in instances]  # Or use serializers
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def destroy(self, request, *args, **kwargs):
        '''
        Confirm that deleting is not allowed
        '''
        return Response(
            {"detail": "Deleting users is not allowed. Mark them as inactive instead."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )
    
    @action(detail=False, methods=['get'], url_path='meta')
    def get_meta(self, request):
        '''
        Get labels for the front end to assure consistency.
        '''
        return Response({
            "roles": get_enum_choices(User.Role),
        })

    @action(detail=False, methods=['get'], url_path='get-favorites')
    def get_favorites(self, request):
        '''
        Action to retreive all of a users favorited objects.
        '''
        user = request.user
        favorites = FavoriteObject.objects.filter(user=user)


        data = {
            'favorites': FavoriteObjectSerializer(favorites, many=True).data,
        }
        return Response(data, status=status.HTTP_200_OK)
    
    @action(detail=False, methods=['post'], url_path='is-favorited')
    def is_favorited(self, request):
        user= request.user
        model_str = request.data.get('model')
        obj_id = request.data.get('id')

        if not model_str or not obj_id:
            return Response({"detail": "Model and ID are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        response = get_favorited_object(model_str, obj_id)
        if not response.get('success', False):
            return Response(response.get('data', {'detail': 'Invalid information provided.'}), status=status.HTTP_400_BAD_REQUEST)
        model = response.get('data')

        is_favorited = FavoriteObject.objects.filter(user=user, content_type=ContentType.objects.get_for_model(model), object_id=obj_id).exists()
        print(is_favorited)
        return Response({'favorited': is_favorited}, status=status.HTTP_200_OK)


    @action(detail=False, methods=['post'], url_path='favorite')
    def favorite(self, request, pk=None):
        '''
        Action to favorite an object (takes app.model + id)
        '''
        user = request.user
        
        model_str = request.data.get('model')
        obj_id = request.data.get('id')

        if not model_str or not obj_id:
            return Response({"detail": "Model and ID are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        response = get_favorited_object(model_str, obj_id)
        if not response.get('success', False):
            return Response(response.get('data', {'detail': 'Invalid information provided.'}), status=status.HTTP_400_BAD_REQUEST)
        model = response.get('data')

        favorite, created = FavoriteObject.objects.get_or_create(
            user=user,
            content_type= ContentType.objects.get_for_model(model),
            object_id=obj_id
        )

        if created:
            return Response({'detail': 'Project favorited.'}, status=status.HTTP_201_CREATED)
        return Response({'detail': 'Project was already favorited.'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['delete'], url_path='unfavorite')
    def unfavorite(self, request, pk=None):
        '''
        Action to unfavorite an object (takes app.model + id)
        '''
        user = request.user
        model_str = request.data.get('model')
        obj_id = request.data.get('id')

        if not model_str or not obj_id:
            return Response({"detail": "Model and ID are required."}, status=status.HTTP_400_BAD_REQUEST)
        
        response = get_favorited_object(model_str, obj_id)
        if not response.get('success', False):
            return Response(response.get('data', {'detail': 'Invalid information provided.'}), status=status.HTTP_400_BAD_REQUEST)
        model = response.get('data')
        content_type= ContentType.objects.get_for_model(model)

        deleted, _ = FavoriteObject.objects.filter(
            user=user,
            content_type=content_type,
            object_id=obj_id
        ).delete()

        if deleted:
            return Response({'detail': 'Project unfavorited.'}, status=status.HTTP_200_OK)
        return Response({'detail': 'Project was not favorited.'}, status=status.HTTP_404_NOT_FOUND)
