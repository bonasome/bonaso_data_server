from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, Target
from organizations.models import Organization
from indicators.models import Indicator
from datetime import date
User = get_user_model()

class ProjectViewSetTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.user3 = User.objects.create_user(username='testuser3', password='testpass', role='meofficer')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        self.client.force_authenticate(user=self.admin)
        self.org = Organization.objects.create(name='Test Org')
        self.org2 = Organization.objects.create(name='Test Org 2')
        self.org3 = Organization.objects.create(name='Test Org 3', parent_organization=self.org2)
        
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.admin.organization = self.org
        self.user2.organization = self.org2
        self.user3.organization = self.org3

        self.project1 = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project1.organizations.set([self.org, self.org2])

        self.project2 = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.project2.organizations.set([self.org, self.org2])

        self.ind = Indicator.objects.create(code='1', name='Test Ind')
        self.ind2 = Indicator.objects.create(code='2', name='Test Ind 2')
        self.project1.indicators.set([self.ind, self.ind2])

    def test_anon(self):
        self.client.logout()
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, 401)
    
    def test_view_only(self):
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

    def test_project_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_search_projects(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/projects/', {'search': 'Beta'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'Beta Project')

    def test_project_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/manage/projects/{self.project2.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.project2.id)
        self.assertEqual(response.data['name'], 'Beta Project')

    def test_view_inactive_not_admin(self):
        self.client.force_authenticate(user=self.user2)
        url = f'/api/manage/projects/{self.project2.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_view_wrong_project(self):
        self.client.force_authenticate(user=self.user3)
        url = f'/api/manage/projects/{self.project2.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_project(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2025-01-01',
            'end': '2025-12-31',
            'description': 'Testing creation',
            'organization_id': [self.org.id],
            'indicator_id': [self.ind.id, self.ind2.id]
        }

        response = self.client.post('/api/manage/projects/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Optional: validate the actual object
        project = Project.objects.get(name='New Project')
        self.assertEqual(project.client, self.client_obj)
        self.assertEqual(project.organizations.count(), 1)
        self.assertEqual(project.organizations.first(), self.org)
        self.assertEqual(project.indicators.count(), 2)
        self.assertEqual(project.created_by, self.admin)

        invalid_payload = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2025-01-01',
            'end': '2024-12-31',
            'description': 'Testing bad creation',
            'organization_id': [self.org.id],
            'indicator_id': [self.ind.id, self.ind2.id]
        }

        invalid_payload2 = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'I dunno',
            'start': '2025-01-01',
            'end': '2024-12-31',
            'description': 'Testing bad creation',
            'organization_id': [self.org.id],
            'indicator_id': [self.ind.id, self.ind2.id]
        }
        response = self.client.post('/api/manage/projects/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post('/api/manage/projects/', invalid_payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_invalid_create(self):
        self.client.force_authenticate(user=self.user3)
        valid_payload = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2025-01-01',
            'end': '2025-12-31',
            'description': 'Testing creation',
            'organization_id': [self.org.id],
            'indicator_id': [self.ind.id, self.ind2.id]
        }
        response = self.client.post('/api/manage/projects/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_put_project(self):
        valid_put = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2025-01-01',
            'end': '2025-12-31',
            'description': 'Testing creation',
            'organization_id': [self.org.id, self.org2.id],
            'indicator_id': [self.ind2.id]
        }
        self.client.force_authenticate(user=self.admin)
        response = self.client.put(f'/api/manage/projects/{self.project1.id}/', valid_put, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.project1.refresh_from_db()
        self.assertEqual(self.project1.organizations.count(), 2)
        self.assertEqual(self.project1.indicators.count(), 1)

    def test_patch_project(self):
        valid_patch = {
            'status': Project.Status.COMPLETED,
            'organization_id': [self.org.id],
        }
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f'/api/manage/projects/{self.project1.id}/', valid_patch, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.project1.refresh_from_db()
        self.assertEqual(self.project1.organizations.count(), 1)
        self.assertEqual(self.project1.status, Project.Status.COMPLETED)

class TaskViewSetTask(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.user3 = User.objects.create_user(username='testuser3', password='testpass', role='meofficer')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')
        self.client.force_authenticate(user=self.admin)
        self.org = Organization.objects.create(name='Test Org')
        self.org2 = Organization.objects.create(name='Test Org 2')
        self.org3 = Organization.objects.create(name='Test Org 3', parent_organization=self.org2)
        
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.admin.organization = self.org
        self.user2.organization = self.org2
        self.user3.organization = self.org3

        self.project1 = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project1.organizations.set([self.org, self.org2, self.org3])

        self.project2 = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.project2.organizations.set([self.org, self.org2])

        self.ind = Indicator.objects.create(code='1', name='Test Ind')
        self.ind2 = Indicator.objects.create(code='1', name='Test Ind 2')

        self.project1.indicators.set([self.ind, self.ind2])

        self.task = Task.objects.create(project=self.project1, organization=self.org2, indicator=self.ind)
        self.task2 = Task.objects.create(project=self.project2, organization=self.org, indicator=self.ind)

    def test_anon(self):
        self.client.logout()
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, 401)

    def test_view_only(self):
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

    def test_project_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_task_filter_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/tasks/?project={self.project1.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_project_list_not_admin(self):
        self.client.force_authenticate(user=self.user2)
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_project_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/manage/tasks/{self.task.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.task.id)
        self.assertEqual(response.data['organization']['id'], self.org2.id)
    
    def test_task_create(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'organization_id': self.org2.id,
            'indicator_id': self.ind2.id,
            'project_id': self.project1.id,
        }

        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_task_invalid_create(self):
        self.client.force_authenticate(user=self.admin)
        
        invalid_payload2 = {
            'organization_id': self.org2.id,
            'indicator_id': self.ind2.id,
            'project_id': self.project2.id,
        }
        response = self.client.post('/api/manage/tasks/', invalid_payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_task_no_create_perm(self):
        self.client.force_authenticate(user=self.user2)
        valid_payload = {
            'organization_id': self.org2.id,
            'indicator_id': self.ind2.id,
            'project_id': self.project2.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_clone_task_valid(self):
        self.client.force_authenticate(user=self.user2)
        valid_payload = {
            'parent_task': self.task.id,
            'organization_id': self.org3.id
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_clone_task_invalid(self):
        self.client.force_authenticate(user=self.user2)
        invalid_payload = {
            'parent_task': self.task.id,
            'organization_id': self.org.id,
            'indicator_id': self.task.indicator.id,
            'project_id': self.task.project.id,
        }
        response = self.client.post('/api/manage/tasks/', invalid_payload, format='json')

class TargetViewSet(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.user3 = User.objects.create_user(username='testuser3', password='testpass', role='meofficer')
        
        self.client.force_authenticate(user=self.admin)
        self.org = Organization.objects.create(name='Test Org')
        self.org2 = Organization.objects.create(name='Test Org 2')
        self.org3 = Organization.objects.create(name='Test Org 3', parent_organization=self.org2)
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.admin.organization = self.org
        self.user2.organization = self.org2
        self.user3.organization = self.org3

        self.project1 = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project1.organizations.set([self.org, self.org2, self.org3])

        self.project2 = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.project2.organizations.set([self.org, self.org2])

        self.ind = Indicator.objects.create(code='1', name='Test Ind')
        self.ind2 = Indicator.objects.create(code='1', name='Test Ind 2')

        self.project1.indicators.set([self.ind, self.ind2])

        self.task = Task.objects.create(project=self.project1, organization=self.org2, indicator=self.ind)
        self.task2 = Task.objects.create(project=self.project2, organization=self.org2, indicator=self.ind)
        self.task3 = Task.objects.create(project=self.project2, organization=self.org, indicator=self.ind)
        self.task4 = Task.objects.create(project=self.project2, organization=self.org, indicator=self.ind2)

        self.target = Target.objects.create(task=self.task, start=date(2025, 5, 1), end=date(2025, 5, 30))
        self.target2 = Target.objects.create(task=self.task2, start=date(2025, 6, 1), end=date(2025, 6, 30))
        self.target3 = Target.objects.create(task=self.task3, start=date(2026, 6, 1), end=date(2026, 6, 30))
    
    def test_anon(self):
        self.client.logout()
        response = self.client.get('/api/manage/targets/')
        self.assertEqual(response.status_code, 401)

    def test_view_only(self):
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/manage/targets/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

    def test_target_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/targets/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    def test_target_filter_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/targets/?task={self.task.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_target_date_filter_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/targets/?start=2025-06-01&end=2025-06-30')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_target_list_not_admin(self):
        self.client.force_authenticate(user=self.user2)
        response = self.client.get('/api/manage/targets/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_target_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/manage/targets/{self.target.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.target.id)
        self.assertEqual(response.data['task']['id'], self.task.id)
    
    def test_target_create(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'task_id': self.task.id,
            'start': date(2026, 8, 1),
            'end': date(2026, 8, 30),
            'amount': 10,
        }
        valid_payload2 = {
            'task_id': self.task3.id,
            'start': date(2026, 8, 1),
            'end': date(2026, 8, 30),
            'related_to_id': self.task4.id,
            'percentage_of_related': 75,
        }

        response = self.client.post('/api/manage/targets/', valid_payload, format='json')
        if response.status_code != 201:
            print(response.status_code)
            print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.post('/api/manage/targets/', valid_payload2, format='json')
        if response.status_code != 201:
            print(response.status_code)
            print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_target_invalid_create(self):
        self.client.force_authenticate(user=self.admin)
        
        invalid_payload = {
            'task_id': self.task.id,
            'start': date(2025, 8, 1),
            'end': date(2024, 8, 30),
            'amount': 10,
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload2 = {
            'task_id': self.task2.id,
            'start': date(2025, 6, 1),
            'end': date(2025, 6, 30),
            'amount': 10,
        }
        response = self.client.post('/api/manage/targets/', invalid_payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload3 = {
            'task_id': self.task.id,
            'start': date(2026, 9, 1),
            'end': date(2026, 9, 30),
            'amount': 10,
            'related_to_id': self.task2.id,
            'percentage_of_related': 75
        }
        response = self.client.post('/api/manage/targets/', invalid_payload3, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_target_no_create_perm(self):
        self.client.force_authenticate(user=self.user2)
        valid_payload = {
            'task_id': self.task.id,
            'start': date(2026, 8, 1),
            'end': date(2026, 8, 30),
            'amount': 10,
        }
        response = self.client.post('/api/manage/targets/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    