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
from flags.models import Flag



class ProfileViewSet(RoleRestrictedViewSet):
    '''
    Manages all endpoints related to managing user profiles (though not passwords/user creation)
    '''
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
        activity = get_user_activity(user) #queryset of objects a user has created/updated

        response_data = {}
        for model_label, instances in activity.items():
            response_data[model_label] = []
            for instance in instances:
                #get basic info
                info = {
                    'display_name': str(instance), 
                    'id': instance.id
                }
                #send both a correct id(s) so the frontend can direct the user to the correct page for review
                if model_label.lower() in [
                    'projects.task', 
                    'projects.projectactivity', 
                    'projects.projectdeadline',
                ]:
                    info['parent'] = instance.project.id
                    if model_label.lower() in ['projects.task']:
                        info['second_parent'] = instance.organization_id
                elif model_label.lower() in ['projects.target']:
                    info['parent'] = instance.project_id
                    info['second_parent'] = instance.organization_id
                elif model_label.lower() in ['respondents.interaction']:
                    info['parent'] = instance.respondent_id
                else:
                    info['parent'] = None
                    info['second_parent'] = None
                
                #track what the user did with this object (created, updated) and at what times
                if 'created_by' in [f.name for f in instance._meta.get_fields()]:
                    info['created'] = True if instance.created_by == user else False
                else: 
                    info['created'] = False

                if 'updated_by' in [f.name for f in instance._meta.get_fields()]:
                    info['updated'] = True if instance.updated_by == user else False
                else: 
                    info['updated'] = False

                if 'created_at' in [f.name for f in instance._meta.get_fields()]:
                    info['created_at'] = instance.created_at
                else:
                    info['created_at'] = None
                if 'updated_at' in [f.name for f in instance._meta.get_fields()]:
                    info['updated_at'] = instance.created_at
                else:
                    info['updated_at'] = None
                
                
                response_data[model_label].append(info)
        
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
        roles = get_enum_choices(User.Role)
        roles = [r for r in roles if r['value'] not in ['supervisor', 'view_only']]
        return Response({
            "roles": roles,
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
        '''
        Check if a user has favorited an item so the frontend can display the correct information on 
        the detail page. With app.model + id
        '''
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
