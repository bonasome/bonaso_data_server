from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views import View
from django.forms.models import model_to_dict
from rest_framework.viewsets import ModelViewSet
from rest_framework import filters
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied
from rest_framework import generics
from django.db.models import Q
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action
from users.restrictviewset import RoleRestrictedViewSet
from rest_framework import serializers
from rest_framework import status

import json
from datetime import datetime, date
today = date.today().isoformat()

from projects.models import Project, ProjectIndicator, ProjectOrganization, Client, Task, Target
from projects.serializers import ProjectListSerializer, ProjectDetailSerializer, TaskSerializer, TargetSerializer

class TaskViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = TaskSerializer
    filter_backends = [filters.SearchFilter, OrderingFilter]
    ordering_fields = ['indicator__code']
    search_fields = ['indicator__code', 'indicator__name', 'project__name', 'organization__name']
    filterset_fields = ['project', 'organization', 'indicator']

    
    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        user_org = getattr(user, 'organization', None)
        queryset = Task.objects.all()

        org_param = self.request.query_params.get('organization')
        if org_param:
            queryset = queryset.filter(organization__id=org_param)

        if role == 'admin':
            return queryset
        elif role in ['meofficer', 'manager'] and user_org:
            return queryset.filter(Q(organization=user_org) | Q(organization__parent_organization=user_org), project__status=Project.Status.ACTIVE)
        elif role in ['data_collector'] and user_org:
            return queryset.filter(organization=user_org, project__status=Project.Status.ACTIVE)
        else:
            return Task.objects.none()

    def create(self, request, *args, **kwargs):
        from organizations.models import Organization
        from indicators.models import Indicator

        user = request.user
        data = request.data
        role = getattr(user, 'role', None)
        user_org = getattr(user, 'organization', None)

        if not role or not user_org:
            raise PermissionDenied('You do not have permission to perform this action.')

        org_id = data.get('organization_id')
        indicator_id = data.get('indicator_id')
        project_id = data.get('project_id')

        if not all([org_id, indicator_id, project_id]):
            raise serializers.ValidationError("All of organization_id, indicator_id, and project_id are required.")

        if role == 'admin':
            try:
                organization = Organization.objects.get(id=org_id)
                indicator = Indicator.objects.get(id=indicator_id)
                project = Project.objects.get(id=project_id)
            except (Organization.DoesNotExist, Indicator.DoesNotExist, Project.DoesNotExist):
                return Response({'detail': 'Related object not found.'}, status=400)

            if not project.organizations.filter(id=organization.id).exists() or not project.indicators.filter(id=indicator.id).exists():
                return Response({'detail': 'Related objects not available in this project.'}, status=400)

            task = Task.objects.create(
                organization=organization,
                indicator=indicator,
                project=project,
                created_by=user,
            )
            return Response(self.get_serializer(task).data, status=201)

        elif role in ['meofficer', 'manager']:
            # Non-admins can assign tasks to child orgs with assigned indicators
            valid_org_ids = Organization.objects.filter(parent_organization=user_org).values_list('id', flat=True)
            valid_indicator_ids = Task.objects.filter(organization=user_org).values_list('indicator__id', flat=True)
            valid_project_ids = Project.objects.filter(organizations=user_org).values_list('id', flat=True)

            if int(org_id) not in valid_org_ids:
                raise PermissionDenied('You may only assign tasks to your child organizations.')
            if int(indicator_id) not in valid_indicator_ids:
                raise PermissionDenied('You may only assign indicators you also have.')
            if int(project_id) not in valid_project_ids:
                raise PermissionDenied('You can only assign tasks to projects you are part of.')

            try:
                organization = Organization.objects.get(id=org_id)
                indicator = Indicator.objects.get(id=indicator_id)
                project = Project.objects.get(id=project_id)
            except (Organization.DoesNotExist, Indicator.DoesNotExist, Project.DoesNotExist):
                raise serializers.ValidationError("One or more provided IDs are invalid.")

            new_task = Task.objects.create(
                project=project,
                organization=organization,
                indicator=indicator,
                created_by=user
            )
            return Response(self.get_serializer(new_task).data, status=201)

        else:
            raise PermissionDenied('You do not have permission to perform this action.')
        

class ProjectViewSet(RoleRestrictedViewSet):
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, OrderingFilter]
    filterset_fields = ['client', 'start', 'end', 'status']
    ordering_fields = ['name','start', 'end', 'client']
    search_fields = ['name', 'description'] 
    queryset = Project.objects.none()
    serializer_class = ProjectDetailSerializer
    def get_serializer_class(self):
        if self.action == 'list':
            return ProjectListSerializer
        else:
            return ProjectDetailSerializer

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)

        if role == 'admin':
            queryset = Project.objects.all()
            status = self.request.query_params.get('status')
            if status:
                queryset = queryset.filter(status=status)
            return queryset

        elif role and org:
            return Project.objects.filter(organizations=org, status=Project.Status.ACTIVE)

        return Project.objects.none()
    
    def create(self, request, *args, **kwargs):
        if request.user.role != 'admin':
            raise PermissionDenied("Only admins can create projects.")
        return super().create(request, *args, **kwargs)
    
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
    
    def partial_update(self, request, *args, **kwargs):
        from organizations.models import Organization
        user = request.user
        instance = self.get_object()

        if user.role != 'admin':
            allowed_keys = ['organization_id']
            if not any(k in request.data for k in allowed_keys):
                raise PermissionDenied("Only admins can edit projects.")

            new_org_ids = request.data.get('organization_id') or []
            if not isinstance(new_org_ids, list):
                new_org_ids = [new_org_ids]

            existing_orgs = set(instance.organizations.values_list('id', flat=True))

            new_orgs = Organization.objects.filter(id__in=new_org_ids).exclude(id__in=existing_orgs)
            invalid_orgs = [org for org in new_orgs if org.parent_organization != user.organization]
            if invalid_orgs:
                raise PermissionDenied("You may only add your subgrantees.")
            instance.organizations.add(*new_orgs)

            return Response(ProjectDetailSerializer(instance, context=self.get_serializer_context()).data)

        return super().partial_update(request, *args, **kwargs)
    
    @action(detail=False, methods=['get'], url_path='meta')
    def filter_options(self, request):
        statuses = [status for status, _ in Project.Status.choices]
        clients = Client.objects.values('id', 'name')
        return Response({
            'statuses': statuses,
            'clients': list(clients) if clients else None,
        })
    @action(detail=True, methods=['delete'], url_path='remove-organization/(?P<organization_id>[^/.]+)')
    def remove_organization(self, request, pk=None, organization_id=None):
        project = self.get_object()
        try:
            org = ProjectOrganization.objects.get(project=project, organization__id=organization_id)
            org.delete()
            return Response({"detail": "Organization removed."}, status=status.HTTP_200_OK)
        except ProjectOrganization.DoesNotExist:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['delete'], url_path='remove-indicator/(?P<indicator_id>[^/.]+)')
    def remove_indicator(self, request, pk=None, indicator_id=None):
        project = self.get_object()
        try:
            indicator = ProjectIndicator.objects.get(project=project, indicator__id=indicator_id)
            indicator.delete()
            return Response({"detail": "Indicator removed."}, status=status.HTTP_200_OK)
        except ProjectIndicator.DoesNotExist:
            return Response({"detail": "Indicator not found."}, status=status.HTTP_404_NOT_FOUND)







class TargetViewSet(RoleRestrictedViewSet):
    queryset = Target.objects.none()
    filter_backends = [filters.SearchFilter, OrderingFilter]
    filterset_fields = ['task', 'organization', 'indicator']
    permission_classes = [IsAuthenticated]
    serializer_class = TargetSerializer
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        role = getattr(user, 'role', None)
        org = getattr(user, 'organization', None)
        if not role or not org:
            return Target.objects.none()
        
        if role == 'admin':
            queryset= Target.objects.all()
        else:
            queryset= Target.objects.filter(task__organization=org)
            queryset = queryset.filter(task__project__status=Project.Status.ACTIVE)

        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        if start:
            queryset = queryset.filter(start__gte=start)
        if end:
            queryset = queryset.filter(end__lte=end)

        return queryset
    
    def create(self, request, *args, **kwargs):
        user = request.user
        if getattr(user, 'role', None) != 'admin':
            raise PermissionDenied("Only admins can create targets.")
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        user = request.user
        if getattr(user, 'role', None) != 'admin':
            raise PermissionDenied("Only admins can update targets.")
        
        # Let DRF handle both PUT and PATCH via super()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
'''
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

class ProjectTasks(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, pk):
        from respondents.models import Interaction
        user = self.request.user
        if user.role != 'admin':
            return
        tasks = Task.objects.filter(project_id=pk).order_by('organization')
        interactions = Interaction.objects.filter(task__in=tasks).order_by('task')
        targets = Target.objects.filter(task__in=tasks).order_by('task')
        data = {}

        for task in tasks:
            orgID = task.organization.id
            if orgID not in data:
                data[orgID] = {
                    'id': orgID,
                    'name': task.organization.name,
                    'tasks': {}
                }

            indicatorID = task.indicator.id
            if indicatorID not in data[orgID]['tasks']:
                data[orgID]['tasks'][indicatorID] = {
                    'task': task.id,
                    'id': indicatorID,
                    'code': task.indicator.code,
                    'name': task.indicator.name,
                    'interactions': [],
                    'targets': []
                }
        for interaction in interactions:
            orgID = interaction.task.organization.id
            indicatorID = interaction.task.indicator.id
            data[orgID]['tasks'][indicatorID]['interactions'].append({
                'id': interaction.id,
                'respondent': interaction.respondent.id,
                'date': interaction.interaction_date,
                'category_id': interaction.subcategory.id if interaction.subcategory else None,
                'category_name': interaction.subcategory.name if interaction.subcategory else None,
            })
        print(targets)
        for target in targets:
            orgID = target.task.organization.id
            indicatorID = interaction.task.indicator.id
            data[orgID]['tasks'][indicatorID]['targets'].append({
                'id': target.id,
                'amount': target.amount,
                'start': target.start,
                'end': target.end,
            })
        for org in data.values():
            org['tasks'] = list(org['tasks'].values())

        return JsonResponse({'organizations': list(data.values())}, safe=False)
            


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
'''