from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics
from datetime import datetime, timedelta
from django.utils import timezone


import json

from indicators.models import Indicator, IndicatorSubcategory
from indicators.serializers import IndicatorsSerializer

class CreateIndicator(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        from projects.models import ProjectIndicator
        messages = []
        user=request.user
        data = json.loads(request.body)
        form = data['formData']
        code = form['code']
        name = form['name']
        desc = form['description']
        status = form['status']
        #codes should be unique so check if one exists
        checkIndicator = Indicator.objects.filter(code=code)
        if checkIndicator:
            messages.append(f'An indicator with code {code} already exists.')
            return JsonResponse({'status': 'warning', 'message': messages })
        indicator = Indicator(code=code, name=name, status=status, description=desc, created_by=user)
        indicator.save()
        return JsonResponse({'status': 'success', 'redirect_id': indicator.id})

class GetModelInfo(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        statusLabels = []
        statusValues = []
        for value, label in Indicator.status.field.choices:
            statusValues.append(value)
            statusLabels.append(label)
        data = {
            'values': {
                'status': statusValues,
            },
            'labels': {
                'status': statusLabels,
            }
        }

        return JsonResponse(data, safe=False)      

class GetList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = IndicatorsSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        if role != 'admin':
            raise PermissionDenied(
                'Only admins may access indicators.'
            )
        query = self.request.query_params.get('q', '')
        return Indicator.objects.filter(name__icontains=query).order_by('name')

class GetIndicator(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, pk, resp):
        from respondents.models import Respondent, Interaction
        from projects.models import Task
        user=self.request.user
        org = user.organization
        indicator = Indicator.objects.filter(id=pk, status='Active').first()
        options = IndicatorSubcategory.objects.filter(indicator=indicator)
        tasks = Task.objects.filter(indicator=indicator)
        preReqTasks = Task.objects.filter(indicator=indicator.prerequisite)
        respondent = Respondent.objects.filter(id=resp).first()
        prereqInteractions = Interaction.objects.filter(task__in=preReqTasks, respondent=respondent)
            
        data=({
            'indicator': {
                'id': indicator.id,
                'code': indicator.code,
                'name': indicator.name,
                'description': indicator.description,
                'prerequisite': None,
                'options': [],
                'interactions':[],
            }
        })
        if indicator.prerequisite:
            data['indicator']['prerequisite'] = {
                'id': indicator.prerequisite.id,
                'code': indicator.prerequisite.code,
                'name': indicator.prerequisite.name,
                'prerequisite_interactions': [],
            }
            for interaction in prereqInteractions:
                data['indicator']['prerequisite']['prerequisite_interactions'].append({
                    'id': interaction.id,
                    'respondent': interaction.respondent.id,
                    'category': interaction.subcategory,
                    'date': interaction.interaction_date,
                })
        for option in options:
            data['indicator']['options'].append({
                'id': option.id,
                'name': option.name,
                'code': option.code,
            })
        print(data)
        twelve_months_ago = timezone.now() - timedelta(days=365)
        for task in tasks:
            interactions = Interaction.objects.filter(task=task, interaction_date__gte=twelve_months_ago)
            for interaction in interactions:
                if interaction.prerequisite:
                    prereq = {
                        'code': interaction.task.indicator.prerequisite.code,
                        'name': interaction.task.indicator.prerequisite.name,
                        'id': interaction.prerequisite.id,
                        'date': interaction.prerequisite.interaction_date,
                    }
                else: prereq = None
                if interaction.created_by:
                    org = interaction.created_by.organization.name
                else:
                    org=None
                if interaction.subcategory:
                    categoryID =  interaction.subcategory.id
                    categoryName = interaction.subcategory.name
                else:
                    categoryID = None
                    categoryName = None
                data['indicator']['interactions'].append({
                    'id': interaction.id,
                    'date': interaction.interaction_date,
                    'category_id': categoryID,
                    'category_name': categoryName, 
                    'organization': org,
                    'prerequisite': prereq,
                })
        return JsonResponse(data, safe=False)