from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics

import json
from datetime import datetime

from projects.models import Project, ProjectIndicator, ProjectOrganization, Client, Task
from projects.serializers import ProjectsSerializer, ProjectIndicatorSerializer, ProjectOrganizationSerializer, ProjectTaskSerializer

class CreateProject(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        messages = []
        user=request.user
        data = json.loads(request.body)
        form = data['formData']

        name = form['name']
        status = form['status']
        clientID = form['client']
        desc = form['description']
        start = form['start']
        end = form['end']
        #codes should be unique so check if one exists
        checkName = Project.objects.filter(name=name)
        if checkName:
            messages.append(f'A project with name {name} already exists. Please give this project a new unqiue one.')
        #client (if provided) should be a valid client instance

        client=None
        if clientID != '':
            client = Client.objects.filter(id=clientID).first()
            if not client:
                messages.append(f'The client provided is not a valid client instance. Please double check this field.')
         
        #confirm date values are dates
        try:
            datetime.strptime(start, '%Y-%m-%d')
        except ValueError:
            messages.append(f'Project start date is not a valid date. Please double check this field.')
        try:
            datetime.strptime(end, '%Y-%m-%d')
        except ValueError:
            messages.append(f'Project end date is not a valid date. Please double check this field.')
        
        if start >= end:
            messages.append(f'Project end date must be after its start date. Plese double check that start and end dates were filled in correctly.')
        if len(messages) > 0:
            return JsonResponse({'status': 'warning', 'message': messages })
        
        project = Project(name=name, status=status, description=desc, client=client, start=start, end=end, created_by=user)
        project.save()

        return JsonResponse({'status': 'success', 'redirect_id': project.id})

class GetModelInfo(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        clients = Client.objects.all()
        clientLabels = []
        clientValues = []
        for client in clients:
            clientLabels.append(client.name)
            clientValues.append(client.id)
        statusLabels = []
        statusValues = []
        for value, label in Project.status.field.choices:
            statusValues.append(value)
            statusLabels.append(label)
        data = {
            'values': {
                'status': statusValues,
                'clients': clientValues,
            },
            'labels': {
                'status': statusLabels,
                'clients': clientLabels,
            }
        }

        return JsonResponse(data, safe=False)

class GetList(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectsSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        if role != 'admin':
            raise PermissionDenied(
                'Only admins may access indicators.'
            )
        return Project.objects.all()

class GetProjectIndicators(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectIndicatorSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        if role != 'admin':
            raise PermissionDenied(
                'Only admins may access indicators.'
            )
        pk = self.kwargs.get('pk')
        return ProjectIndicator.objects.filter(project_id=pk)

class AddProjectIndicator(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        from indicators.models import Indicator
        messages = []
        user=request.user
        if user.role != 'admin':
            return
        data = json.loads(request.body)
        print(data)
        indicatorID = data['indicator']
        projectID = data['project']
        indicator = Indicator.objects.filter(id=indicatorID).first()
        project = Project.objects.filter(id=projectID).first()
        if not indicator:
            return
        checkInProject = ProjectIndicator.objects.filter(indicator=indicator, project=project).first()
        if checkInProject:
            messages.append(f'Indicator is already in project.')
            return JsonResponse({'status': 'warning', 'message': messages })
        projectInd = ProjectIndicator(project=project, indicator=indicator)
        projectInd.save()
        return JsonResponse({'status': 'success', 'message': [f'Indicator {indicator.code} added to project!']})

class GetProjectOrgs(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectOrganizationSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        if role != 'admin':
            raise PermissionDenied(
                'Only admins may add organizations to projects.'
            )
        pk = self.kwargs.get('pk')
        return ProjectOrganization.objects.filter(project_id=pk)  

class AddProjectOrg(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        from organizations.models import Organization
        messages = []
        user=request.user
        if user.role != 'admin':
            return
        data = json.loads(request.body)
        print(data)
        orgID = data['organization']
        projectID = data['project']
        org = Organization.objects.filter(id=orgID).first()
        project = Project.objects.filter(id=projectID).first()
        if not org:
            return
        checkInProject = ProjectOrganization.objects.filter(organization=org, project=project).first()
        if checkInProject:
            messages.append(f'Organization is already in project.')
            return JsonResponse({'status': 'warning', 'message': messages })
        projectOrg = ProjectOrganization(project=project, organization=org)
        projectOrg.save()
        return JsonResponse({'status': 'success', 'message': [f'Organizaton {org.name} added to project!']})

class GetProjectTasks(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectTaskSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        if role != 'admin':
            raise PermissionDenied(
                'Only admins may access tasks.'
            )
        pk = self.kwargs.get('pk')
        return Task.objects.filter(project_id=pk)
    
class AddTask(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        from organizations.models import Organization
        from indicators.models import Indicator
        messages = []
        user=request.user
        if user.role != 'admin':
            return
        data = json.loads(request.body)
        print(data)
        indicatorCode = data['indicator']
        orgID = data['organization']
        projectID = data['project']
        indicator = Indicator.objects.filter(code=indicatorCode).first()
        org = Organization.objects.filter(id=orgID).first()
        project = Project.objects.filter(id=projectID).first()

        if not org or not project or not indicator:   
            return
        checkInProject = Task.objects.filter(organization=org, project=project, indicator=indicator).first()
        if checkInProject:
            messages.append(f'Task already assigned.')
            return JsonResponse({'status': 'warning', 'message': messages })
        task = Task(project=project, organization=org, indicator=indicator)
        task.save()
        return JsonResponse({'status': 'success', 'message': [f'Indicator {indicator.code} assigned to {org.name} for project!']})

#this is the view the lay user uses to access tasks
class MyTasks(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = self.request.user
        org = user.organization
        tasks = Task.objects.filter(organization=org)
        projects = Project.objects.filter(organization=org, status='Active')
        print(projects)
        data = {
            'projects': [],
        }
        project_map = {}

        for project in projects:
            proj_data = {
                'id': project.id,
                'name': project.name,
                'indicators': [],
            }
            data['projects'].append(proj_data)
            project_map[project.id] = proj_data

        # Attach indicators by project
        for task in tasks:
            project_id = task.project.id
            if project_id in project_map:
                indicator = task.indicator
                project_map[project_id]['indicators'].append({
                    'task': task.id,
                    'id': indicator.id,
                    'code': indicator.code,
                    'name': indicator.name,
                    'description': indicator.description,
                })
        print(data)
        return JsonResponse(data, safe=False)