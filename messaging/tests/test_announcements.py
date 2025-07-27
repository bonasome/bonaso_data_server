from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
User = get_user_model()

from projects.models import Project, Client, ProjectOrganization
from organizations.models import Organization
from messaging.models import Announcement, AnnouncementOrganization
from datetime import date

class AnnouncementViewSetTest(APITestCase):
    '''
    This is a general test for project adjacent things (activities, deadlines) since they mostly 
    share the same logic/permission classes.

    We're not testing these as rigorously yet since these are nice to have and not critical to the data 
    collection.Just make sure the basics work.
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
        self.project.organizations.set([self.parent_org, self.other_org, self.child_org])

        child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        child_link.parent_organization = self.parent_org
        child_link.save()

        self.public_announcement = Announcement.objects.create(
            visible_to_all=True,
            cascade_to_children=False,
            subject='Test Public',
            body='nerds',
            sent_by=self.admin
        )

        self.announcement_child = Announcement.objects.create(
            project=self.project,
            visible_to_all=False,
            cascade_to_children=False,
            subject='Test Other',
            body='LeBron JAMES!!!',
            sent_by=self.officer
        )
        self.announcement_child.organizations.set([self.child_org])

        self.announcement_other = Announcement.objects.create(
            project=self.project,
            visible_to_all=False,
            cascade_to_children=False,
            subject='Test Other',
            body='LeBron JAMES!!!',
            sent_by=self.admin
        )
        self.announcement_other.organizations.set([self.other_org])
        

    def test_admin_view(self):
        '''
        Admins can view all related activities
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/messages/announcements/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_higher_role_view(self):
        '''
        Higher roles can only see public (visible to all) or activities scoped to them and their child orgs
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/messages/announcements/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_lower_role_view(self):
        '''
        Lower roles can only see public (visible to all) or for their org specifically
        '''
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/messages/announcements/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        
    def test_admin_all(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'visible_to_all': True,
            'subject': 'Parent Test Create',
            'body': 'LeBron JAMES!!!',
        }
        response = self.client.post('/api/messages/announcements/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_parent(self):
        '''
        Higher roles can create announcements for their org and their children.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'project_id': self.project.id,
            'visible_to_all': False,
            'cascade_to_children': True,
            'subject': 'Parent Test Create',
            'body': 'LeBron JAMES!!!',
        }
        response = self.client.post('/api/messages/announcements/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = Announcement.objects.filter(subject='Parent Test Create').first()
        self.assertEqual(created.organizations.count(), 2)


    def test_me_perms(self):
        '''
        Non admins cannot create events for unrelated orgs.
        '''
        self.client.force_authenticate(user=self.manager)
        invalid_payload_1 = {
            'visible_to_all': True,
            'cascade_to_children': True,
            'subject': 'Parent Test Create',
            'body': 'LeBron JAMES!!!',
        }
        response = self.client.post('/api/messages/announcements/', invalid_payload_1, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        invalid_payload_2 = {
            'visible_to_all': False,
            'cascade_to_children': True,
            'subject': 'Parent Test Create',
            'body': 'LeBron JAMES!!!',
            'organization_ids': [self.other_org.id]
        }
        response = self.client.post('/api/messages/announcements/', invalid_payload_2, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)