from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from events.models import Event, EventOrganization, EventTask, DemographicCount
from projects.models import Project, Client, Task, ProjectOrganization
from respondents.models import Respondent, Interaction
from organizations.models import Organization
from indicators.models import Indicator, IndicatorSubcategory
from datetime import date, timedelta

User = get_user_model()

class DemographicCountsTest(APITestCase):
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
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
        self.project.organizations.set([self.parent_org, self.other_org, self.child_org])

        child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        child_link.parent_organization = self.parent_org
        child_link.save()

        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.subcats_indicator = Indicator.objects.create(code='3', name='Subcats')
        self.category1 = IndicatorSubcategory.objects.create(name='Cat 1')
        self.category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        self.subcats_indicator.subcategories.set([self.category1, self.category2])

        self.prerequsite_indicator = Indicator.objects.create(code='p', name='Prereq')
        self.child_indicator = Indicator.objects.create(code='c', name='Child')
        self.child_indicator.prerequisites.set([self.prerequsite_indicator])
        
        self.task = Task.objects.create(indicator=self.indicator, project=self.project, organization=self.parent_org)
        self.child_task = Task.objects.create(indicator=self.indicator, project=self.project, organization=self.child_org)
        self.subcats_task = Task.objects.create(indicator=self.subcats_indicator, project=self.project, organization=self.parent_org)
        self.prereq_task = Task.objects.create(indicator=self.prerequsite_indicator, project=self.project, organization=self.child_org)
        self.dependent_task = Task.objects.create(indicator=self.child_indicator, project=self.project, organization=self.child_org)
        
        self.event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-09',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task, self.subcats_task, self.prereq_task, self.dependent_task, self.child_task])
        self.event.organizations.set([self.parent_org, self.child_org])

        self.event_future = Event.objects.create(
            name='Event',
            start=date.today()+timedelta(days=1),
            end=date.today()+timedelta(days=2),
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task, self.subcats_task, self.prereq_task, self.dependent_task, self.child_task])
        self.event.organizations.set([self.parent_org, self.child_org])
    
    def test_count_creation(self):
        '''
        Test a basic count creation
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.subcats_task.id,
                    'subcategory_id': self.category1.id,
                    'organization_id': self.parent_org.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        counts = DemographicCount.objects.filter(event=self.event)
        count = DemographicCount.objects.filter(event=self.event).first()
        self.assertEqual(counts.count(), 1)
        self.assertEqual(count.count, 25)
        self.assertEqual(count.created_by, self.admin)
    
    def test_count_update(self):
        '''
        Test a flow of creating a count then updating it.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.subcats_task.id,
                    'subcategory_id': self.category1.id,
                    'organization_id': self.parent_org.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        valid_payload = {
            'counts': [
                {
                    'count': 30, #change only the count, system should handle it
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.subcats_task.id,
                    'subcategory_id': self.category1.id,
                    'organization_id': self.parent_org.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        counts = DemographicCount.objects.filter(event=self.event)
        count = DemographicCount.objects.filter(event=self.event).first()
        self.assertEqual(counts.count(), 1) #make sure the count wasn't duplicated
        self.assertEqual(count.count, 30)
    
    def test_count_update_shift_bd(self):
        '''
        We enforce one task, one count, so if the breakdowns change, we delete old breakdowns that are now 
        considered obselete and replace them with the new count.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        valid_payload = {
            'counts': [
                {
                    'count': 34, #breakdowns changed, so the old one is now considered obselete
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'task_id': self.task.id, #task stayed the same so its not considered "new"
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        counts = DemographicCount.objects.filter(event=self.event)
        count = DemographicCount.objects.filter(event=self.event).first()
        self.assertEqual(counts.count(), 1)
        self.assertEqual(count.count, 34)
        self.assertEqual(count.created_by, self.admin)

    def test_count_perm(self):
        '''
        A manager should be able to edit counts for their own tasks and their children.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        #should also work
        valid_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.child_task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_count_associate(self):
        '''
        Associates should be allowed to edit counts for an event they are in, but they should not be allowed to 
        edit counts for tasks for other orgs.
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.child_task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
        valid_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_perm_fail_dc(self):
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_future(self):
        '''
        If an event has not happened yet, there should not be counts associated with it.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.task.id,
                },
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event_future.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_rows(self):
        '''
        If the same row is uploaded twice, this should throw an error, since we don't know which count is
        intended.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.task.id,
                },
                {
                    'count': 25,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_prereq(self):
        '''
        A count with no prereq count task in the event should cause a flag.
        '''
        self.client.force_authenticate(user=self.admin)
        flagged_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.dependent_task.id, #this task has a prereq
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', flagged_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        counts = DemographicCount.objects.filter(event=self.event)
        self.assertEqual(counts.count(), 1)
        count = counts.first()
        flag = count.flags
        self.assertEqual(count.count, 35)
        self.assertEqual(flag.count(), 1)

    def test_mismatched_nums_prereq(self):
        '''
        If a count has a prerequisite and its number for a given count is higher than its parents given count,
        that should throw a flag. Correcting the value should also autocorrect the flag.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 25,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.prereq_task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = DemographicCount.objects.filter(event=self.event, task=self.prereq_task).first()
        self.assertEqual(count.count, 25)
        flagged_payload = {
            'counts': [
                {
                    'count': 50,
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.dependent_task.id,
                },
                {
                    'count': 51,
                    'sex': 'F',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.dependent_task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', flagged_payload, content_type='application/json')
        counts = DemographicCount.objects.filter(event=self.event, task=self.dependent_task)
        self.assertEqual(counts.count(), 2)
        count1 = DemographicCount.objects.filter(count=50).first()
        count2 = DemographicCount.objects.filter(count=51).first()
        flag1 = count1.flags.first()
        self.assertIn(f'The amount of this count is greater than its corresponding prerequisite', flag1.reason)
        flag2 =count2.flags.first()
        self.assertIn(f'that does not have an associated count', flag2.reason)

        #updating the parent counts should cascade and resolve the flags
        resolve_payload = {
            'counts': [
                {
                    'count': 50, #correct parent to fix child task
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.prereq_task.id,
                },
                {
                    'count': 73, #uplaod a prereq
                    'sex': 'F',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'status': 'staff',
                    'task_id': self.prereq_task.id,
                },
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', resolve_payload, content_type='application/json')
        print(response.json())
        counts = DemographicCount.objects.filter(event=self.event)
        self.assertEqual(counts.count(), 4)
        flag1 = count1.flags.first()
        self.assertEqual(flag1.resolved, True)
        self.assertEqual(flag1.auto_flagged, True)
        flag2 = count2.flags.first()
        self.assertEqual(flag2.resolved, True)
        self.assertEqual(flag2.auto_flagged, True)
