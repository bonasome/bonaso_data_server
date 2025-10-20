from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, ProjectOrganization
from respondents.models import Respondent, Interaction
from organizations.models import Organization
from indicators.models import Assessment
from datetime import date
User = get_user_model()


class ProjectViewSetTest(APITestCase):
    '''
    Testing the basic project meta, mostly living in the project serializer, mostly
    testing basic perms.
    '''
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org

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
        self.project.organizations.set([self.parent_org, self.other_org])

        self.planned_project = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.planned_project.organizations.set([self.parent_org, self.other_org])

        self.non_client = Project.objects.create(
            name='Beta Project',
            client=self.other_client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Third project',
            created_by=self.admin,
        )

        self.assessment = Assessment.objects.create(name='Ass')
        self.task = Task.objects.create(assessment=self.assessment, project=self.project, organization=self.parent_org)
        
    
    def test_admin_view(self):
        '''
        Admins should see all projects
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    def test_me_mgr_view(self):
        '''
        Higher roles should only see active projects that they are a member of.
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_client_view(self):
        '''
        Clients should see projects they are the client for, but not others.
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_create_project(self):
        '''
        Admins are allowed to create projects using a payload like the one below.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2025-01-01',
            'end': '2025-12-31',
            'description': 'Testing creation',
        }
        response = self.client.post('/api/manage/projects/', valid_payload, format='json')
        project = Project.objects.get(name='New Project')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(project.created_by, self.admin)

    def test_simple_patch(self):
        '''
        Admins can also patch projects.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'start': '2024-02-01',
            'client_id': self.other_client_obj.id
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.client, self.other_client_obj)
        self.assertEqual(self.project.updated_by, self.admin)
    
    def test_create_project_perm(self):
        '''
        No one else though.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2025-01-01',
            'end': '2025-12-31',
            'description': 'Testing creation',
        }
        response = self.client.post('/api/manage/projects/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_perm(self):
        '''
        Patches should not work either, even for clients who own the project.
        '''
        self.client.force_authenticate(user=self.client_user)
        valid_payload = {
            'start': '2024-02-01',
            'client_id': self.other_client_obj.id
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_invalid_project(self):
        '''
        Invalid dates should trigger an error.
        '''
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'name': 'New Project',
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2026-01-01',
            'end': '2025-12-31',
            'description': 'Testing creation',
        }
        response = self.client.post('/api/manage/projects/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #should trigger missing field error
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'client_id': self.client_obj.id,
            'status': 'Active',
            'start': '2025-01-01',
            'end': '2025-12-31',
            'description': 'Testing creation',
        }
        response = self.client.post('/api/manage/projects/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_patch(self):
        '''
        Bad patch should also trigger a 400.
        '''
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'start': '2027-02-01',
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_project(self):
        '''
        Admins can delete projects.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.planned_project.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_delete_project_active(self):
        '''
        Active Projects cannot be deleted
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
    
    def test_delete_project_data(self):
        '''
        Projects with interactions/counts also cannot be deleted.
        '''
        self.client.force_authenticate(user=self.admin)
        respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district=Respondent.District.CENTRAL,
            citizenship='test',
            sex=Respondent.Sex.FEMALE,
        )
        interaction = Interaction.objects.create(task=self.task, respondent=respondent, interaction_date='2025-06-23', interaction_location='There')
        self.project.status = Project.Status.COMPLETED
        self.project.save()
        
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_delete_project_perm(self):
        '''
        Non admins cannot delete.
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class ProjectOrganizationViewSetTest(APITestCase):
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.other_user = User.objects.create_user(username='rando', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org
        self.view_user.organization = self.parent_org
        self.other_user.organization = self.other_org
        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)

        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent_org])

        self.project_2 = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project_2.organizations.set([self.parent_org, self.other_org])

        self.planned_project = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.planned_project.organizations.set([self.parent_org])

        self.assessment = Assessment.objects.create(name='Ass')
        self.task = Task.objects.create(assessment=self.assessment, project=self.project, organization=self.parent_org)
    
    def test_admin_add_org(self):
        '''
        Admins should be allowed to add an organizaiton to a project.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload ={
            'organization_id': [self.other_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.planned_project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.planned_project.refresh_from_db()
        self.assertEqual(self.planned_project.organizations.count(), 2)

    def test_admin_add_org_multiple(self):
        '''
        Admins should be allowed to add an organizaiton to a project.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload ={
            'parent_id': self.parent_org.id,
            'child_ids': [self.other_org.id, self.child_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project_2.id}/assign-subgrantee/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        print(response.json())
        self.assertEqual(len(response.data['reassigned']), 1)
        self.assertEqual(len(response.data['added']), 1)
        self.planned_project.refresh_from_db()
        self.assertEqual(self.project_2.organizations.count(), 3)
    
    def test_me_mgr_add_org(self):
        '''
        Rather than directly edit project details, other users can assign subgrantees via a special method.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload ={
            'parent_id': self.parent_org.id,
            'child_ids': [self.child_org.id],
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/assign-subgrantee/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.organizations.count(), 2)

        #doing this should fail
        valid_payload ={
            'organization_id': [self.child_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_me_mgr_existing_org(self):
        '''
        They can't assign an org as a subgrantee if they're already in the project.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload ={
            'parent_id': self.parent_org.id,
            'child_ids': [self.other_org.id],
        }
        response = self.client.patch(f'/api/manage/projects/{self.project_2.id}/assign-subgrantee/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    
    def test_dc_org(self):
        '''
        Lower levels should not be allowed to manage organizations.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload ={
            'parent_id': self.parent_org.id,
            'child_ids': [self.other_org.id],
        }
        response = self.client.patch(f'/api/manage/projects/{self.project_2.id}/assign-subgrantee/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_remove_org_cleanup(self):
        '''
        Admins are allowed to remove an org from a project. It should also clean up tasks if applicable.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.parent_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Task.objects.filter(project=self.project).count(), 0)
    
    def test_remove_child_org(self):
        '''
        ME Officers can remove their child orgs from a project
        '''
        self.client.force_authenticate(user=self.manager)
        #assing them
        valid_payload ={
            'parent_id': self.parent_org.id,
            'child_ids': [self.child_org.id],
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/assign-subgrantee/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.organizations.count(), 2)

        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.child_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.organizations.count(), 1)
    
    def test_remove_self(self):
        '''
        An organization cannot remove themselves from a project.
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.parent_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def remove_with_data(self):
        '''
        An organization with active tasks (interactions or counts associated with them) cannot be removed.
        '''
        self.client.force_authenticate(user=self.admin)
        respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district=Respondent.District.CENTRAL,
            citizenship='test',
            sex=Respondent.Sex.FEMALE,
        )
        interaction = Interaction.objects.create(task=self.task, respondent=respondent, interaction_date='2025-06-23', interaction_location='There')
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.parent_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
