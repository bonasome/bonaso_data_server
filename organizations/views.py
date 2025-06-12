from django.shortcuts import render, redirect
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics

from organizations.models import Organization
from organizations.serializers import OrgsSerializer

class GetList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrgsSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        if role != 'admin':
            raise PermissionDenied(
                'Only admins may add organizations to a project.'
            )
        query = self.request.query_params.get('q', '')
        return Organization.objects.filter(name__icontains=query).order_by('name')
