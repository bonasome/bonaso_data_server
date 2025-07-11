from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from events.models import Event, EventOrganization, EventTask, DemographicCount
from projects.models import Project, Client, Task
from respondents.models import Respondent, Interaction
from organizations.models import Organization
from indicators.models import Indicator, IndicatorSubcategory
from datetime import date

User = get_user_model()


class EventViewSetTest(APITestCase):
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
        self.child_org = Organization.objects.create(name='Child', parent_organization=self.parent_org)
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
        self.project.organizations.set([self.parent_org, self.other_org])

        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.new_indicator = Indicator.objects.create(code='2', name='New')
        
        self.project.indicators.set([self.indicator])
        self.task = Task.objects.create(indicator=self.indicator, project=self.project, organization=self.parent_org)
        self.child_task = Task.objects.create(indicator=self.indicator, project=self.project, organization=self.child_org)
        self.new_task = Task.objects.create(indicator=self.new_indicator, project=self.project, organization=self.parent_org)
        self.other_task = Task.objects.create(indicator=self.indicator, project=self.project, organization=self.other_org)

        self.event = Event.objects.create(
            name='Event',
            event_date='2024-07-09',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task])
        self.event.organizations.set([self.parent_org])

        self.other_event = Event.objects.create(
            name='Event',
            event_date='2024-07-09',
            location='here',
            host=self.other_org
        )
        self.other_event.organizations.set([self.other_org])
        self.other_event.tasks.set([self.other_task])

    def test_admin_view(self):
        #admin should see both projects
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_me_mgr_view(self):
        #meofficer or manager should see the one active project
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_client_view(self):
        #meofficer or manager should see the one active project
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_create_event(self):
        #admin should be able to create a project using a payload similar to the one below
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'event_date': '2024-03-01',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_id': [self.task.id],
            'organization_id': [self.child_org.id],

        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(name='New Event')
        self.assertEqual(event.created_by, self.admin)
        self.assertEqual(event.tasks.count(), 1)
        self.assertEqual(event.organizations.count(), 1)

    def test_patch_event(self):
        #admin should be able to edit details
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'event_date': '2024-03-02',
            'task_id': [self.new_task.id],
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.event_date, date(2024, 3, 2))
        self.assertEqual(self.event.tasks.count(), 2)
    
    def test_create_event_perm(self):
        #should work
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'event_date': '2024-03-01',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_id': [self.task.id],
            'organization_id': [self.child_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        #should not work, wrong host
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'event_date': '2024-03-01',
            'location': 'Gaborone',
            'host_id': self.other_org.id,
            'description': 'Testing creation',
            'task_id': [self.task.id],
            'organization_id': [self.child_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        #should not work, adding bad orgs
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'event_date': '2024-03-01',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_id': [self.task.id],
            'organization_id': [self.other_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        #should not work, adding bad tasks
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'event_date': '2024-03-01',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_id': [self.other_task.id],
            'organization_id': [self.parent_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_event_perm(self):
        #should work
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'event_date': '2024-02-01',
            'organization_id': [self.child_org.id],
            'task_id': [self.child_task.id]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.event_date, date(2024, 2, 1))
    
        #should fail
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'event_date': '2024-02-01',
            'organization_id': [self.other_org.id],
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        #should also fail
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'event_date': '2024-02-01',
            'organization_id': [self.parent_org.id],
        }
        response = self.client.patch(f'/api/activities/events/{self.other_event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def test_delete_event(self):
        #admins are allowed to delete projects
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/activities/events/{self.other_event.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_delete_event_no_perm(self):
        #admins are allowed to delete projects
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/activities/events/{self.event.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_remove_org(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/activities/events/{self.other_event.id}/remove-organization/{self.other_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.other_event.refresh_from_db()
        self.assertEqual(self.other_event.organizations.count(), 0)
    
    def test_remove_task(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/activities/events/{self.event.id}/remove-task/{self.task.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.tasks.count(), 0)
    
    def test_associated_perms(self):
        test_event = Event.objects.create(
            name='Event',
            event_date='2024-07-09',
            location='here',
            host=self.parent_org
        )
        test_event.tasks.set([self.task, self.child_task])
        test_event.organizations.set([self.parent_org, self.child_org])

        #child org should be allowed to see since they are a part of the event
        self.client.force_authenticate(user=self.officer)
        response = self.client.get(f'/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        #but not edit
        valid_payload = {
            'event_date': '2024-02-01',
        }
        
        response = self.client.patch(f'/api/activities/events/{test_event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        #or remove
        response = self.client.delete(f'/api/activities/events/{test_event.id}/remove-task/{self.child_task.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.delete(f'/api/activities/events/{test_event.id}/remove-organization/{self.child_org.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
        self.child_org = Organization.objects.create(name='Child', parent_organization=self.parent_org)
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
        self.project.organizations.set([self.parent_org, self.other_org])

        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.subcats_indicator = Indicator.objects.create(code='3', name='Subcats')
        self.category1 = IndicatorSubcategory.objects.create(name='Cat 1')
        self.category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        self.subcats_indicator.subcategories.set([self.category1, self.category2])

        self.prerequsite_indicator = Indicator.objects.create(code='p', name='Prereq')
        self.child_indicator = Indicator.objects.create(code='c', name='Child', prerequisite=self.prerequsite_indicator)
        
        self.project.indicators.set([self.indicator, self.subcats_indicator, self.prerequsite_indicator, self.child_indicator])
        self.task = Task.objects.create(indicator=self.indicator, project=self.project, organization=self.parent_org)
        self.child_task = Task.objects.create(indicator=self.indicator, project=self.project, organization=self.child_org)
        self.subcats_task = Task.objects.create(indicator=self.subcats_indicator, project=self.project, organization=self.parent_org)
        self.prereq_task = Task.objects.create(indicator=self.prerequsite_indicator, project=self.project, organization=self.child_org)
        self.dependent_task = Task.objects.create(indicator=self.child_indicator, project=self.project, organization=self.child_org)
        
        self.event = Event.objects.create(
            name='Event',
            event_date='2024-07-09',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task, self.subcats_task, self.prereq_task, self.dependent_task])
        self.event.organizations.set([self.parent_org, self.child_org])
    
    def test_count_creation(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': False,
                    'hiv_status': True,
                    'sex': 'M',
                    'age_range': 'under_18',
                    'citizenship': 'citizen',
                    'status': 'Staff',
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
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': False,
                    'hiv_status': True,
                    'sex': 'M',
                    'age_range': 'under_18',
                    'citizenship': 'citizen',
                    'status': 'Staff',
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
                    'count': 30,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': False,
                    'hiv_status': True,
                    'sex': 'M',
                    'age_range': 'under_18',
                    'citizenship': 'citizen',
                    'status': 'Staff',
                    'task_id': self.subcats_task.id,
                    'subcategory_id': self.category1.id,
                    'organization_id': self.parent_org.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        counts = DemographicCount.objects.filter(event=self.event)
        count = DemographicCount.objects.filter(event=self.event).first()
        self.assertEqual(counts.count(), 1)
        self.assertEqual(count.count, 30)
        self.assertEqual(count.updated_by, self.admin)
    
    def test_no_prereq(self):
        #unlike one offs with respondents, lack of prereqs will not be rejected (to preserve work/account for flexibility)
        #but it should be flagged
        self.client.force_authenticate(user=self.admin)
        flagged_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': 'under_18',
                    'citizenship': 'citizen',
                    'status': 'Staff',
                    'task_id': self.dependent_task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', flagged_payload, content_type='application/json')
        counts = DemographicCount.objects.filter(event=self.event)
        self.assertEqual(counts.count(), 1)
        count = DemographicCount.objects.filter(event=self.event, task=self.dependent_task).first()
        self.assertEqual(count.count, 35)
        self.assertEqual(count.flagged, True)

    def test_count_flagging(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'counts': [
                {
                    'count': 25,
                    'sex': 'M',
                    'age_range': 'under_18',
                    'citizenship': 'citizen',
                    'status': 'Staff',
                    'task_id': self.prereq_task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        count = DemographicCount.objects.filter(event=self.event, task=self.prereq_task).first()
        self.assertEqual(count.count, 25)
        self.assertEqual(count.flagged, False)
        flagged_payload = {
            'counts': [
                {
                    'count': 35,
                    'sex': 'M',
                    'age_range': 'under_18',
                    'citizenship': 'citizen',
                    'status': 'Staff',
                    'task_id': self.dependent_task.id,
                }
            ]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/update-counts/', flagged_payload, content_type='application/json')
        counts = DemographicCount.objects.filter(event=self.event)
        self.assertEqual(counts.count(), 2)
        count = DemographicCount.objects.filter(event=self.event, task=self.dependent_task).first()
        self.assertEqual(count.count, 35)
        self.assertEqual(count.flagged, True)
