from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, Target
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus
from organizations.models import Organization
from indicators.models import Indicator, IndicatorSubcategory
from datetime import date, timedelta
User = get_user_model()

class InteractionViewSetTest(APITestCase):
    def setUp(self):
        self.today = date.today().isoformat()

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

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.other_client_obj = Client.objects.create(name='Loser Client', created_by=self.admin)

        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2025-01-01',
            end='2025-12-31',
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

        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.prereq_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)

        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.indicator)
        self.other_task =Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator)

        self.inactive_task = Task.objects.create(project=self.planned_project, organization=self.parent_org, indicator=self.indicator)

        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        self.respondent2= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        self.respondent3= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

        self.interaction = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, task=self.task, created_by=self.data_collector)
        self.interaction2 = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent2, task=self.task, created_by=self.officer)
        self.interaction_child = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, task=self.child_task)
        self.interaction_other = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, task=self.other_task)
    
    def test_interaction_admin_view(self):
        #admin should see all interactions
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 4)
    
    def test_interaction_other_view(self):
        #as should everyone
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 4)
    
    def test_create_interaction(self):
        #test creation works with this payload (though rarely used in create views)
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_interaction_child(self):
        #test that higher ranks can create for children
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'task': self.child_task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_interaction_child(self):
        #but dc can't
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.child_task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_interaction(self):
        #dc can patch own interactions
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_patch_interaction_no_perm(self):
        #but not others, even within their own org
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction2.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_interaction_me_mgr(self):
        #higher ranks can edit interactions for themselves/children
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_child.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_patch_interaction_no_perm(self):
        #but not other orgs
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_interaction_no_perm(self):
        #admins can do whatever
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_patch_interaction_bad_dates(self):
        self.client.force_authenticate(user=self.admin)
        tomorrow = date.today() + timedelta(days=1)
        invalid_payload = {
            'interaction_date': tomorrow,
        }
        #date can't be in the future
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        
        invalid_payload = {
            'interaction_date': '2024-06-02',
        }
        #date can't be in the future
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'interaction_date': '2025-063-p',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_interaction(self):
        #admin can delete interaction
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/record/interactions/{self.interaction_other.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_interaction_no_perm(self):
        #but no one else
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/record/interactions/{self.interaction.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_no_prereq(self):
        #should fail since respondent3 has no interaction realted to task
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.prereq_task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #try again with prereq and it should work
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.prereq_task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_prereq_dates(self):
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        #prereq has task, but date is before
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.prereq_task.id,
            'interaction_date': '2025-06-12',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #try again with proper date
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.prereq_task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_interaction_forgot_subcats(self):
        self.client.force_authenticate(user=self.data_collector)
        ind1 = Indicator.objects.create(code='10', name='GimmeDemSubcats')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        ind1.subcategories.set([category])
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind1)
        valid_payload = {
            'task': task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #try again with subcats
        valid_payload = {
            'task': task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
            'subcategory_names': ['Cat 1']
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_interaction_mismatched_subcat(self):
        self.client.force_authenticate(user=self.data_collector)
        ind1 = Indicator.objects.create(code='10', name='ParentSubcat')
        ind2 = Indicator.objects.create(code='11', name='ChildSubcat', prerequisite=ind1)
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind1.subcategories.set([category, category2])
        ind2.subcategories.set([category, category2])

        task_parent = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind1)
        task_child = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind2)

        #categories are wrong, so it should fail
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': task_parent.id,
            'subcategory_names': ['Cat 1']
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': task_child.id,
            'subcategory_names': ['Cat 1', 'Cat 2']
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #try again with matched categories
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': task_child.id,
            'subcategory_names': ['Cat 1']
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_interaction_forgot_number(self):
        #if the indicator requires a number, not including it should trigger a fail
        self.client.force_authenticate(user=self.data_collector)
        ind = Indicator.objects.create(code='10', name='GimmeANummie', require_numeric=True)
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind)
        valid_payload = {
            'task': task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #not quite there
        valid_payload = {
            'task': task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
            'numeric_component': 'oops I forgot the number'
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #there we go
        valid_payload = {
            'task': task.id,
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
            'numeric_component': 5
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    

    def test_no_flag(self):
        #interactions 30 days away or greater should not be flagged
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 5, 5),
            'respondent': self.respondent3.id,
            'task': self.task.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 7),
            'respondent': self.respondent3.id,
            'task': self.task.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        interaction = Interaction.objects.get(interaction_date=date(2025, 6, 7), task=self.task, respondent=self.respondent3)
        print(interaction.flagged)
        self.assertFalse(interaction.flagged)

    def test_flag(self):
        #interactions within 30 days should be flagged automatically. They can be unflagged later after review. 
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 5),
            'respondent': self.respondent3.id,
            'task': self.task.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 7),
            'respondent': self.respondent3.id,
            'task': self.task.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        interaction = Interaction.objects.get(interaction_date=date(2025, 6, 7), task=self.task, respondent=self.respondent3)
        self.assertTrue(interaction.flagged)
    #test bulk create

    def test_bulk_create(self):
        self.client.force_authenticate(user=self.data_collector)
        
        ind_number = Indicator.objects.create(code='4', name='Numeric Ind', require_numeric=True)
        ind_subcat = Indicator.objects.create(code='10', name='GimmeDemSubcats')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind_subcat.subcategories.set([category, category2])
        
        task_number = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_number)
        task_subcat = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat)
        
        response = self.client.post('/api/record/interactions/batch/', {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent3.id,
            'tasks': [
                {'task': self.task.id},
                {'task': task_number.id, 'numeric_component': 10},
                {'task': task_subcat.id, 'subcategory_names': ['Cat 1', 'Cat 2']}
            ]
        }, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_bulk_create_edge(self):
        self.client.force_authenticate(user=self.data_collector)
        
        ind_number = Indicator.objects.create(code='4', name='Numeric Ind', require_numeric=True)
        ind_subcat = Indicator.objects.create(code='10', name='GimmeDemSubcats')
        ind_subcat_prereq = Indicator.objects.create(code='11', name='GimmeDemSubcatsV2')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind_subcat.subcategories.set([category, category2])
        ind_subcat_prereq.subcategories.set([category, category2])
        task_number = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_number)
        task_subcat = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat)
        task_subcat_prereq = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat_prereq)
        response = self.client.post('/api/record/interactions/batch/', {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent3.id,
            'tasks': [
                {'task': self.task.id},
                {'task': task_number.id, 'numeric_component': 10},
                {'task': task_subcat_prereq.id, 'subcategory_names': ['Cat 1', 'Cat 2']},
                {'task': task_subcat.id, 'subcategory_names': ['Cat 1', 'Cat 2']}
            ]
        }, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)