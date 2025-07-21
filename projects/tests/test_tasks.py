from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, Target, ProjectOrganization
from respondents.models import Respondent, Interaction
from organizations.models import Organization
from indicators.models import Indicator
from datetime import date
User = get_user_model()


class TaskViewSetTest(APITestCase):
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        self.loser_org = Organization.objects.create(name='Not Invited')

        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org
        self.view_user.organization = self.parent_org
        self.client_user.organization = self.other_org

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.other_client_obj = Client.objects.create(name='Loser Client', created_by=self.admin)

        self.client_user.client_organization = self.client_obj
        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent_org, self.child_org, self.other_org])

        child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        child_link.parent_organization = self.parent_org
        child_link.save()

        self.planned_project = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )

        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.child_indicator = Indicator.objects.create(code='2', name='Child')
        self.child_indicator.prerequisites.set([self.indicator])
        self.not_in_project = Indicator.objects.create(code='3', name='Unrelated')
        
        self.project.indicators.set([self.indicator, self.child_indicator])

        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.other_task = Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator)

        self.inactive_task = Task.objects.create(project=self.planned_project, organization=self.parent_org, indicator=self.indicator)
    
    def test_task_admin_view(self):
        #admins should be able to view all tasks
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    
    def test_task_non_admin(self):
        #non-admins should only see tasks associated with their org and with active projects
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_task_client_view(self):
        #admins should be able to view all tasks
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_task_create_admin(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'organization_id': self.other_org.id,
            'indicator_id': self.child_indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_task_create_wrong_ind(self):
        #if an indicator isn't in a project, you should not be allowed to create a task for it
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'organization_id': self.other_org.id,
            'indicator_id': self.not_in_project.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_task_create_wrong_org(self):
        #same with orgs
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'organization_id': self.loser_org.id,
            'indicator_id': self.indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_task_create_no_prereq(self):
        #need to add prereqs first
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'organization_id': self.child_org.id,
            'indicator_id': self.child_indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        valid_payload = {
            'organization_id': self.child_org.id,
            'indicator_id': self.indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        valid_payload = {
            'organization_id': self.child_org.id,
            'indicator_id': self.child_indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_task_create_child(self):
        #non-admins should be allowed to assign tasks to children, assuming they are in the project
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'organization_id': self.child_org.id,
            'indicator_id': self.indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        #they should also be able to view tasks for child organizations
        response = self.client.get('/api/manage/tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_task_create_dc(self):
        #dc are disbarred from creating tasks
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'organization_id': self.child_org.id,
            'indicator_id': self.indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_task_assign_other(self):
        #but not any others
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'organization_id': self.other_org.id,
            'indicator_id': self.child_indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_task_assign_client(self):
        #but not any others
        self.client.force_authenticate(user=self.client_user)
        valid_payload = {
            'organization_id': self.other_org.id,
            'indicator_id': self.child_indicator.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_task_assign_self(self):
        #or themselves
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'organization_id': self.parent_org.id,
            'indicator_id': self.not_in_project.id,
            'project_id': self.project.id,
        }
        response = self.client.post('/api/manage/tasks/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_task(self):
        #admin should be allowed to delete tasks
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/tasks/{self.other_task.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_delete_task_prereq(self):
        #unless they are a prerequisite
        child_task = Task.objects.create(organization=self.parent_org, indicator=self.child_indicator, project=self.project)
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/tasks/{self.task.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
    
    def test_delete_task_inter(self):
        #or it is 'active', i.e. it is linked to an interaction
        respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district=Respondent.District.CENTRAL,
            citizenship='test',
            sex=Respondent.Sex.FEMALE,
        )
        interaction = Interaction.objects.create(task=self.task, respondent=respondent, interaction_date='2025-06-23')
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/tasks/{self.task.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
    
    #patching tasks is not really an intended method, but at some point we should write tests to either confirm it works or to disallow it