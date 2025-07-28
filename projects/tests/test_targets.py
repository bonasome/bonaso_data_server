from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, Target, ProjectOrganization
from respondents.models import Respondent, Interaction
from organizations.models import Organization
from indicators.models import Indicator
from flags.utils import create_flag
from datetime import date
User = get_user_model()


class TargetViewSetTest(APITestCase):
    '''
    Viewset for testing target creation/editing/viewing logic. 

    Please note that our aggregation logic is tested in the analysis app under analysis.tests.test_achievement.
    '''
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

        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)

        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.indicator)
        self.other_task = Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator)

        self.inactive_task = Task.objects.create(project=self.planned_project, organization=self.parent_org, indicator=self.indicator)
        
        self.child_target = Target.objects.create(task=self.child_task, amount=50, start='2024-04-01', end='2024-04-30')
        self.target = Target.objects.create(task=self.task, amount=50, start='2024-06-01', end='2024-06-30')
        self.other_target = Target.objects.create(task=self.other_task, amount=50, start='2024-06-01', end='2024-06-30')
        
        self.respondent_full = Respondent.objects.create(
            is_anonymous=False, 
            id_no= '1234567',
            first_name= 'Test',
            last_name= 'Testerson',
            dob= date(2000, 1, 1),
            ward= 'Here',
            village= 'ThePlace', 
            citizenship= 'Test',
            sex= Respondent.Sex.FEMALE,
            district= Respondent.District.CENTRAL,
        )


    def test_target_admin_view(self):
        '''
        Admins should be allowed to view all targets.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/targets/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    
    def test_target_non_admin(self):
        #non-admins should only see targets associated with their org/child orgs and with active projects
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/manage/targets/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_target_create(self):
        '''
        Targets should be created with the payload below.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'task_id': self.task.id,
            'amount': 60,
            'start': '2024-07-01',
            'end': '2024-07-31'
        }
        response = self.client.post('/api/manage/targets/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        target=Target.objects.filter(task=self.task.id, amount=60).first()
        self.assertEqual(target.created_by, self.admin)
    
    def test_target_patch(self):
        '''
        They can also be updated.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'amount': 70,
        }
        response = self.client.patch(f'/api/manage/targets/{self.target.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.amount, 70)
        self.assertEqual(self.target.updated_by, self.admin)
    
    def test_target_create_child(self):
        '''
        Higher roles are allowed to create targets for child orgs.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'task_id': self.child_task.id,
            'amount': 60,
            'start': '2024-07-01',
            'end': '2024-07-31'
        }
        response = self.client.post('/api/manage/targets/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_task_patch_non_child(self):
        '''
        But not others or themsevles.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'amount': 70,
        }
        response = self.client.patch(f'/api/manage/targets/{self.other_target.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        
        valid_payload = {
            'amount': 70,
        }
        response = self.client.patch(f'/api/manage/targets/{self.target.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    
    def test_target_delete_admin(self):
        '''
        Admins are allowed to delete a target.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/manage/targets/{self.target.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_target_delete_non_admin(self):
        '''
        Higher roles can delete targets for their child orgs.
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/manage/targets/{self.child_target.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_target_delete_non_admin_self(self):
        '''
        But not their own targets.
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/manage/targets/{self.target.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    #data validation tests here

    def test_target_create_rel(self):
        '''
        Also make sure that targets can be created with realtive amounts.
        '''
        rel_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)
        interaction1 = Interaction.objects.create(respondent=self.respondent_full, interaction_date=date(2024,7,2), task=self.task, interaction_location='here')
        interaction2 = Interaction.objects.create(respondent=self.respondent_full, interaction_date=date(2024,7,2), task=self.task, interaction_location='here')
        create_flag(instance=interaction2, reason="Test reason", caused_by=self.admin)
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'task_id': rel_task.id,
            'related_to_id': self.task.id,
            'percentage_of_related': 75,
            'start': '2024-07-01',
            'end': '2024-07-31'
        }
        response = self.client.post('/api/manage/targets/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        target = Target.objects.filter(task=rel_task).first()
        response = self.client.get(f'/api/manage/targets/{target.id}/')
        print(response.json())

    def test_target_create_rel_wrong(self):
        rel_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)
        #related to not with same org/project
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'task_id': rel_task.id,
            'related_to_id': self.other_task.id,
            'percentage_of_related': 75,
            'start': '2024-07-01',
            'end': '2024-07-31'
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        #impossible target, like cmon, not cool bro
        invalid_payload = {
            'task_id': rel_task.id,
            'related_to_id': self.task.id,
            'percentage_of_related': 107,
            'start': '2025-07-01',
            'end': '2025-07-31'
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #or referencing self, not allowed and not a bro move
        invalid_payload = {
            'task_id': rel_task.id,
            'related_to_id': rel_task.id,
            'percentage_of_related': 75,
            'start': '2025-07-01',
            'end': '2025-07-31'
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_target_mismatched_amounts(self):
        rel_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'task_id': rel_task.id,
            'amount': 80,
            'related_to_id': self.task.id,
            'percentage_of_related': 75,
            'start': '2025-07-01',
            'end': '2025-07-31'
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        invalid_payload = {
            'task_id': rel_task.id,
            'related_to_id': self.task.id,
            'start': '2025-07-01',
            'end': '2025-07-31'
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_target_create_overlap(self):
        #should fail since there's already a target for this task in this time period
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'task_id': self.task.id,
            'amount': 60,
            'start': '2024-06-01',
            'end': '2024-06-30',
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
    
    def test_target_create_wrong_dates(self):
        #start before end
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'task_id': self.task.id,
            'amount': 60,
            'start': '2025-09-01',
            'end': '2025-05-30',
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #invalid format
        invalid_payload = {
            'task_id': self.task.id,
            'amount': 60,
            'start': '2025-06-012',
            'end': '20253-05-30',
        }
        response = self.client.post('/api/manage/targets/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #on patch too for good measure
        invalid_payload = {

            'end': '2025-05-30',
        }
        response = self.client.patch(f'/api/manage/targets/{self.target.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    