from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, Target
from respondents.models import Respondent, Interaction
from organizations.models import Organization
from indicators.models import Indicator
from datetime import date
User = get_user_model()


class ProjectViewSetTest(APITestCase):
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child', parent_organization=self.parent_org)
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org
        self.view_user.organization = self.parent_org

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.other_client_obj = Client.objects.create(name='Loser Client', created_by=self.admin)

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

        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.child_indicator = Indicator.objects.create(code='2', name='Child', prerequisite=self.indicator)
        self.not_in_project = Indicator.objects.create(code='3', name='Unrelated')
        
        self.project.indicators.set([self.indicator, self.child_indicator])
    
    def test_admin_view(self):
        #admin should see both projects
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_me_mgr_view(self):
        #meofficer or manager should see the one active project
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_no_orgs_match(self):
        #the meofficer from the child org is not in the project, so they should see nothing
        self.client.force_authenticate(user=self.officer)
        response = self.client.get('/api/manage/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 0)
    
    def test_create_project(self):
        #admin should be able to create a project using a payload similar to the one below
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
        #admin should be able to edit details
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
        #admin should be able to create a project using a payload similar to the one below
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
        #no one else should be able to edit project details
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'start': '2024-02-01',
            'client_id': self.other_client_obj.id
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_craeate_invalid_project(self):
        #should trigger date error
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
        #this invalid start date should trigger a 400
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'start': '2027-02-01',
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_project(self):
        #admins are allowed to delete projects
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.planned_project.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_delete_project_active(self):
        #unless they are marked as active
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
    
    def test_delete_project_inter(self):
        #or they have an interaction assoicated with them
        self.client.force_authenticate(user=self.admin)
        respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district=Respondent.District.CENTRAL,
            citizenship='test',
            sex=Respondent.Sex.FEMALE,
        )
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)
        interaction = Interaction.objects.create(task=task, respondent=respondent, interaction_date='2025-06-23')
        self.project.status = Project.Status.COMPLETED
        self.project.save()
        
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_delete_project_perm(self):
        #non-admins have no perm to delete
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class ProjectIndicatorViewSetTest(APITestCase):
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child', parent_organization=self.parent_org)
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org
        self.view_user.organization = self.parent_org

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.other_client_obj = Client.objects.create(name='Loser Client', created_by=self.admin)

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

        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.child_indicator = Indicator.objects.create(code='2', name='Child', prerequisite=self.indicator)
        self.not_in_project = Indicator.objects.create(code='3', name='Unrelated')
        
        self.project.indicators.set([self.indicator, self.child_indicator])
    
    def test_add_indicator(self):
        #admin should be able to add indicators to a project
        self.client.force_authenticate(user=self.admin)
        valid_payload ={
            'indicator_id': [self.not_in_project.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.indicators.count(), 3)
    
    def test_add_no_prereq(self):
        #adding an indicator with a prerequisite without its parent should fail
        self.client.force_authenticate(user=self.admin)
        invalid_payload ={
            'indicator_id': [self.child_indicator.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.planned_project.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.planned_project.refresh_from_db()
        self.assertEqual(self.planned_project.indicators.count(), 0)

    def test_add_with_prereq(self):
        #try again with both and it should work
        self.client.force_authenticate(user=self.admin)
        valid_payload ={
            'indicator_id': [self.child_indicator.id, self.indicator.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.planned_project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.planned_project.refresh_from_db()
        self.assertEqual(self.planned_project.indicators.count(), 2)

    def test_add_indicator_perm(self):
        #other roles should not be allowed to add indicators
        self.client.force_authenticate(user=self.manager)
        valid_payload ={
            'indicator_id': [self.not_in_project.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_indicator(self):
        #admins are allowed to remove indicators from a project
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-indicator/{self.child_indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_remove_indicator_cleanup(self):
        #admins should be allowed to remove an organization from a project
        self.client.force_authenticate(user=self.admin)
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)
        self.assertEqual(len(Task.objects.filter(project=self.project)), 1)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-indicator/{self.child_indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(Task.objects.filter(project=self.project)), 0)

    def test_remove_indicator_perm(self):
        #but no one else
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-indicator/{self.child_indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_indicator_prereq(self):
        #and also not if they are parent to another indicator in the project
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-indicator/{self.indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
    
    def test_remove_indicator_inter(self):
        #and not if they are associated with an active task (has an interaction recorded)
        respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district=Respondent.District.CENTRAL,
            citizenship='test',
            sex=Respondent.Sex.FEMALE,
        )
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)
        interaction = Interaction.objects.create(task=task, respondent=respondent, interaction_date='2025-06-23')

        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-indicator/{self.child_indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


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
        self.child_org = Organization.objects.create(name='Child', parent_organization=self.parent_org)
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
        self.child_indicator = Indicator.objects.create(code='2', name='Child', prerequisite=self.indicator)
        self.not_in_project = Indicator.objects.create(code='3', name='Unrelated')
        
        self.project.indicators.set([self.indicator, self.child_indicator])
    
    def test_admin_add_org(self):
        #admins should be able to add an organization to a project
        self.client.force_authenticate(user=self.admin)
        valid_payload ={
            'organization_id': [self.parent_org.id, self.other_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.planned_project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.planned_project.refresh_from_db()
        self.assertEqual(self.planned_project.organizations.count(), 2)
    
    def test_me_mgr_add_org(self):
        #managers/m&e officers should be allowed to add their children to a project
        self.client.force_authenticate(user=self.manager)
        valid_payload ={
            'organization_id': [self.child_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.organizations.count(), 2)

    def test_me_mgr_wrong_org(self):
        #..but not unrelated orgs
        self.client.force_authenticate(user=self.manager)
        valid_payload ={
            'organization_id': [self.other_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_me_mgr_wrong_org(self):
        #or themselves (they shouldn't even be able to see this project)
        self.client.force_authenticate(user=self.other_user)
        valid_payload ={
            'organization_id': [self.other_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_dc_org(self):
        #dc should also not be allowed to add orgs
        self.client.force_authenticate(user=self.data_collector)
        valid_payload ={
            'organization_id': [self.child_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_non_admin_inactive_proj(self):
        #dc should also not be allowed to add orgs, in fact they shouldn't even be able to see this project
        self.client.force_authenticate(user=self.manager)
        valid_payload ={
            'organization_id': [self.child_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.planned_project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_remove_org(self):
        #admins should be allowed to remove an organization from a project
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.parent_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_remove_org_cleanup(self):
        #admins should be allowed to remove an organization from a project
        self.client.force_authenticate(user=self.admin)
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.assertEqual(len(Task.objects.filter(project=self.project)), 1)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.parent_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(Task.objects.filter(project=self.project)), 0)
    
    def test_remove_child_org(self):
        #me officers/managers should also be allowed to remove their child organizations from projects
        self.client.force_authenticate(user=self.manager)
        valid_payload ={
            'organization_id': [self.child_org.id]
        }
        response = self.client.patch(f'/api/manage/projects/{self.project.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.organizations.count(), 2)

        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.child_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.organizations.count(), 1)
    
    def test_remove_self(self):
        #but not themselves
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.parent_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def remove_with_inter(self):
        #if an organization has an 'active task' (has an interaction) then removing them should be forbidden
        self.client.force_authenticate(user=self.admin)
        respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district=Respondent.District.CENTRAL,
            citizenship='test',
            sex=Respondent.Sex.FEMALE,
        )
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        interaction = Interaction.objects.create(task=task, respondent=respondent, interaction_date='2025-06-23')
        response = self.client.delete(f'/api/manage/projects/{self.project.id}/remove-organization/{self.parent_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
