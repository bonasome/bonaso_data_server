from django.shortcuts import render
from django.contrib.auth import logout
from .serializers import CustomTokenObtainPairSerializer, CustomMobileTokenSerializer
from django.contrib.auth.password_validation import validate_password
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.exceptions import ValidationError
from rest_framework import status
from django.db.models import Q
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from django.contrib.auth import authenticate
from rest_framework.permissions import AllowAny
from datetime import timedelta
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from django.http import HttpResponse
from django.conf import settings
User = get_user_model()

import os
debug = os.getenv("DEBUG", "False").lower() in ["1", "true", "yes"]

class CookieTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    def post(self, request, *args, **kwargs):
        print(f'DEBUG mode (from env): {debug}')
        response = super().post(request, *args, **kwargs)
        data =  response.data
        access_token = data.get('access')
        refresh_token = data.get('refresh')
        
        if access_token and refresh_token:
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure= not debug, 
                samesite='None' if not debug else 'Lax',
                max_age=60*5,
                path='/', 
            )
            response.set_cookie(
                key='refresh_token',
                value=refresh_token,
                httponly=True,
                secure=not debug, 
                samesite='None' if not debug else 'Lax',
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
        if not refresh_token:
            return Response({'detail': 'Refresh token missing.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data={'refresh': refresh_token})
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return Response({'detail': 'Invalid refresh token.'}, status=status.HTTP_401_UNAUTHORIZED)

        access_token = serializer.validated_data.get('access')
        new_refresh_token = serializer.validated_data.get('refresh')

        response = Response({'message': 'Access and refresh tokens refreshed.'})

        if access_token:
            response.set_cookie(
                key='access_token',
                value=access_token,
                httponly=True,
                secure=not debug,
                samesite='None' if not debug else 'Lax',
                max_age=60 * 5
            )

        if new_refresh_token:
            response.set_cookie(
                key='refresh_token',
                value=new_refresh_token,
                httponly=True,
                secure=not debug,
                samesite='None' if not debug else 'Lax',
                max_age=60 * 60 * 8
            )

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
    response = HttpResponse("Logged out successfully")
    samesite_policy = 'None' if not settings.DEBUG else 'Lax'

    refresh_token = request.COOKIES.get('refresh_token')

    if refresh_token:
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            # Token is already blacklisted or invalid
            pass

    response.delete_cookie('access_token', path='/', samesite=samesite_policy)
    response.delete_cookie('refresh_token', path='/', samesite=samesite_policy)

    logout(request)
    return response

class ApplyForNewUser(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        from organizations.models import Organization
        from projects.models import Client
        user = request.user
        if not user or user.role not in ['meofficer', 'manager', 'admin'] or not user.organization:
            return Response({'detail': 'You do not have permission to perform this action.'}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        org_id = data.get('organization', user.organization.id)
        role = data.get('role')
        if not role: 
            role ='view_only'
        try:
            org = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            return Response({'detail': 'Organization not found.'}, status=400)
        if user.role != 'admin':
            if not (org == user.organization or org.parent_organization == user.organization):
                return Response({'detail': 'You do not have permission to create this user.'}, status=403)
        
        username = data.get('username')
        password = data.get('password')

        if not username or not password:
            return Response({'detail': 'Insufficient information provided.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(username=username).exists():
            return Response({'detail': 'A user with that username already exists.'}, status=status.HTTP_409_CONFLICT)
        
        try:
            validate_password(password)
        except ValidationError as e:
            return Response({'detail': e.messages}, status=400)
        client_id = data.get('client_id')
        if user.role=='admin' and client_id:
            client = Client.objects.get(id=client_id)
        else:
            client = None
        new_user = User.objects.create_user(
            username=username,
            password=password,
            first_name=data.get('first_name', ''),
            last_name = data.get('last_name', ''),
            email=data.get('email', ''),
            organization=org,
            role='view_only' if user.role !='admin' else role,
            client_organization=client,
        )
        return Response({'message': 'User created successfuly. An admin will activate them shortly.', 'id': new_user.id}, status=status.HTTP_201_CREATED)

class AdminResetPasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        print('request received')
        admin_user = self.request.user
        if admin_user.role != 'admin':
            return Response({'detail': 'You do not have permission to perform this action.'}, status=status.HTTP_403_FORBIDDEN)
        target_user_id = request.data.get('user_id')
        new_password = request.data.get('new_password')

        try:
            user = User.objects.get(id=target_user_id)
            try:
                validate_password(new_password)
            except ValidationError as e:
                return Response({'errors': e.messages}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(new_password)
            user.save()
            return Response({'detail': 'Password reset successful.'}, status=status.HTTP_200_OK)
        except User.DoesNotExist:
            return Response({'detail': 'User not found.'}, status=status.HTTP_404_NOT_FOUND)
        
class MobileLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = CustomMobileTokenSerializer
    def post(self, request, *args, **kwargs):
        username = request.data.get("username")
        password = request.data.get("password")

        user = authenticate(username=username, password=password)
        if not user:
            return Response({"detail": "Invalid credentials."}, status=401)

        refresh = RefreshToken.for_user(user)
        refresh.access_token.set_exp(lifetime=timedelta(minutes=15))

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user_id": user.id,
        })

class TestConnectionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"}, status=200)