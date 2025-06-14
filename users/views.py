from django.shortcuts import render
from django.contrib.auth import logout
from .serializers import CustomTokenObtainPairSerializer
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from django.contrib.auth import get_user_model
User = get_user_model()

class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        data =  response.data
        access_token = data.get('access')
        refresh_token = data.get('refresh')
        
        if access_token and refresh_token:
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=False, #change this when moving out of dev
                samesite='Lax',
                max_age=60*5,
                path='/', 
            )
            response.set_cookie(
                key='refresh_token',
                value=refresh_token,
                httponly=True,
                secure=False, #change this when moving out of dev
                samesite='Lax',
                max_age=60*60*8,
                path='/',
            )
            del response.data['access']
            del response.data['refresh']
        return response

class CookieTokenRefreshView(TokenRefreshView):
    serializer_class = TokenRefreshSerializer
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get('refresh_token')
        print(refresh_token)
        if not refresh_token:
            return Response({'detail': 'Refresh token missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data={'refresh': refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return Response({'detail': 'Invalid refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)

        access_token = serializer.validated_data.get('access')
        response = Response()
        
        if access_token:
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=False,  # Change to True in prod!
                samesite='Lax',
                max_age=60 * 5
            )
        
        # Optional: return limited user data if needed
        response.data = {'message': 'Access token refreshed.'}
        return response

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user(request):
    user = request.user
    return Response({
        'id': user.id,
        'username': user.username,
        'role': user.role,
        'organization_id': user.organization.id if user.organization else None,
    })

@api_view(['POST'])
def logout_view(request):
    response = Response({'status': 'success', 'message': 'Logged out successfully'}, status=status.HTTP_200_OK)
    response.delete_cookie('access_token')
    response.delete_cookie('refresh_token')
    logout(request)
    return response

class ApplyForNewUser(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        user = request.user
        if not user or user.role not in ['meofficer', 'manager', 'admin'] or not user.organization:
            return Response({'detail': 'You do not have permission to perform this action.'}, status=status.HTTP_400_BAD_REQUEST)
        org = user.organization
        if not org or not org.pk:
            return Response({'detail': 'Invalid or missing organization.'}, status=400)
        
        data = request.data
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return Response({'detail': 'You do not have permission to perform this action.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(username=username).exists():
            return Response({'detail': 'A user with that username already exists.'}, status=status.HTTP_400_BAD_REQUEST)
        
        new_user = User.objects.create_user(
            username=username,
            password=password,
            email=data.get('email', ''),
            organization=user.organization,
            role='view_only',
        )
        return Response({'message': 'User created successfuly. An admin will activate them shortly.'}, status=status.HTTP_201_CREATED)
