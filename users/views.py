from django.shortcuts import render
from users.models import User
from django.contrib.auth import logout
from django.http import JsonResponse

from .serializers import MyTokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import IsAuthenticated

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer

class UserInfo(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        user = request.user
        if not user:
            return JsonResponse({'status': 'error', 'message':['No user.']})
        data= {
            'role': user.role
        }
        return JsonResponse(data, safe=False)
