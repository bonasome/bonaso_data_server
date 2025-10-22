from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from events.models import Event, EventOrganization, EventTask
from projects.models import Project, Client, Task, ProjectOrganization
from organizations.models import Organization
from indicators.models import Indicator
from datetime import date, timedelta

User = get_user_model()


class EventViewSetTest(APITestCase):
    '''
    Primarily a test of the events serailizer, testing perms and logic for events.
    '''
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

        #create a project
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
        
        #set up a child organization structure
        child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        child_link.parent_organization = self.parent_org
        child_link.save()

        #create some indicators and some tasks
        self.indicator_event = Indicator.objects.create(name='Number of Events Held', category=Indicator.Category.EVENTS)
        self.indicator_org = Indicator.objects.create(name='Number of Orgs Trained at Event', category=Indicator.Category.ORGS)

        self.task = Task.objects.create(indicator=self.indicator_event, project=self.project, organization=self.parent_org)
        self.child_task = Task.objects.create(indicator=self.indicator_event, project=self.project, organization=self.child_org)
        self.new_task = Task.objects.create(indicator=self.indicator_event, project=self.project, organization=self.parent_org)
        self.other_task = Task.objects.create(indicator=self.indicator_event, project=self.project, organization=self.other_org)


        #create a few sample events
        self.event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-09',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task])
        self.event.organizations.set([self.parent_org])

        self.other_event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-09',
            location='here',
            host=self.other_org
        )
        self.other_event.organizations.set([self.other_org])
        self.other_event.tasks.set([self.other_task])

        self.third_event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-09',
            location='here',
            host=self.other_org
        )


    def test_admin_view(self):
        '''
        Admin should see everything
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    def test_me_mgr_view(self):
        '''
        Higher roles should see only events that they are related to
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_child_view(self):
        '''
        Participants should see events they are a part of.
        '''
        event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-09',
            location='here',
            host=self.parent_org
        )
        event.tasks.set([self.task])
        event.organizations.set([self.parent_org, self.child_org])

        self.client.force_authenticate(user=self.officer)
        response = self.client.get('/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_client_view(self):
        '''
        Clients should only see projects they are a part of
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/activities/events/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_create_event(self):
        '''
        The below payload should be a valid event payload
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'start': '2024-03-01',
            'end': '2024-03-02',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_ids': [self.task.id],
            'organization_ids': [self.child_org.id],

        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = Event.objects.get(name='New Event')
        self.assertEqual(event.created_by, self.admin)
        self.assertEqual(event.tasks.count(), 1)
        self.assertEqual(event.organizations.count(), 1)

    def test_patch_event(self):
        '''
        Test a new patch. Tasks/orgs should stack.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'start': '2024-07-08',
            'task_ids': [self.task.id, self.new_task.id],
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.start, date(2024, 7, 8))
        self.assertEqual(self.event.tasks.count(), 2)
    
    def test_date_validation(self):
        '''
        Test that start date cannot be after end date.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'start': '2027-07-08',
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_create_event_perm(self):
        '''
        Test a few permissions related to creating events for non-admins. Should be able to create events,
        but not with information related to orgs they are not related to.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'start': '2024-03-01',
            'end': '2024-03-02',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_ids': [self.task.id],
            'organization_ids': [self.child_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        #should not work, wrong host
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'start': '2024-03-01',
            'end': '2024-03-02',
            'location': 'Gaborone',
            'host_id': self.other_org.id,
            'description': 'Testing creation',
            'task_ids': [self.task.id],
            'organization_ids': [self.child_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        #should not work, adding bad orgs
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'start': '2024-03-01',
            'end': '2024-03-02',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_ids': [self.task.id],
            'organization_ids': [self.other_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        #should not work, adding bad tasks
        valid_payload = {
            'name': 'New Event',
            'type': 'Training',
            'start': '2024-03-01',
            'end': '2024-03-02',
            'location': 'Gaborone',
            'host_id': self.parent_org.id,
            'description': 'Testing creation',
            'task_ids': [self.other_task.id],
            'organization_ids': [self.parent_org.id],
        }
        response = self.client.post('/api/activities/events/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_event_perm(self):
        '''
        Test a few permissions related to patcing events for non-admins. Should be able to patch events,
        but not with information related to orgs they are not related to.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'start': '2024-07-01',
            'organization_ids': [self.child_org.id],
            'task_ids': [self.child_task.id]
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.event.refresh_from_db()
        self.assertEqual(self.event.start, date(2024, 7, 1))
    
        #should fail
        valid_payload = {
            'start': '2024-07-01',
            'organization_ids': [self.other_org.id],
        }
        response = self.client.patch(f'/api/activities/events/{self.event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        #should also fail
        valid_payload = {
            'start': '2024-07-01',
            'organization_ids': [self.parent_org.id],
        }
        response = self.client.patch(f'/api/activities/events/{self.other_event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    def patch_event_child(self):
        '''
        Parent orgs should have the ability to edit events for their child orgs.
        '''
        event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-09',
            location='here',
            host=self.child_org
        )
        event.tasks.set([self.child_task])
        event.organizations.set([self.child_org])
        self.client.force_authenticate(user=self.manager)

        valid_payload = {
            'start': '2024-07-01',
        }
        response = self.client.patch(f'/api/activities/events/{event.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.start, date(2024, 7, 1))
    
    def test_delete_event(self):
        '''
        Admins are allowed to delete events.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/activities/events/{self.other_event.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_delete_event_no_perm(self):
        '''
        But not anyone else.
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/activities/events/{self.event.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_associated_perms(self):
        '''
        Associates (in the event, but not the host) should be able to view, but not edit events.
        '''
        test_event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-09',
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
            'start': '2024-07-01',
        }
        
        response = self.client.patch(f'/api/activities/events/{test_event.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

