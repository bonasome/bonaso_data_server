from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
User = get_user_model()

from projects.models import Project, Client, ProjectOrganization
from organizations.models import Organization
from messaging.models import Message, MessageRecipient
from datetime import date

class MessageViewSetTest(APITestCase):
    '''
    This is a general test for project adjacent things (activities, deadlines) since they mostly 
    share the same logic/permission classes.

    We're not testing these as rigorously yet since these are nice to have and not critical to the data 
    collection.Just make sure the basics work.
    '''
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.admin_2 = User.objects.create_user(username='admin_2', password='testpass', role='admin')

        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.other = User.objects.create_user(username='loser', password='testpass', role='manager')

        #set up a parent/child org and an unrelated org
        self.admin_org = Organization.objects.create(name='Admin')
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.admin_org
        self.admin.save()
        self.admin_2.organization = self.admin_org
        self.admin_2.save()
        self.manager.organization = self.parent_org
        self.manager.save()
        self.officer.organization = self.child_org
        self.officer.save()
        self.data_collector.organization = self.parent_org
        self.data_collector.save()
        self.other.organization = self.other_org
        self.other.save()

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



    def test_admin_recip(self):
        '''
        Admins can view all users as recipients
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/messages/dm/recipients/')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 6)
    
    def test_higher_role_recip(self):
        '''
        Higher role can see admin+org+children 2(admin)+2(org)+1(child)
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/messages/dm/recipients/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 5)
    
    def test_lower_role_recip(self):
        '''
        Lower Role can only see admin + org (2 admin + 2 org)
        '''
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/messages/dm/recipients/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 4)
    
    def test_send_to_admin(self):
        '''
        Users can send to admins and all admins are recipients.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'subject': 'Admin Abuse',
            'body': 'Bro',
            'send_to_admin': True,
        }
        response = self.client.post('/api/messages/dm/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        msg = Message.objects.filter(subject='Admin Abuse').first()
        self.assertEqual(msg.recipients.count(), 2)
    
    def test_send_read_complete_pl(self):
        '''
        Test the full process of sending, reading, and completing a message.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'subject': 'Dew the dew',
            'body': 'Bro',
            'recipient_data': [{'id': self.data_collector.id, 'actionable': True}, {'id': self.officer.id, 'actionable': False}] 
        }
        response = self.client.post('/api/messages/dm/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        msg = Message.objects.filter(subject='Dew the dew').first()
        self.assertEqual(msg.recipients.count(), 2)

        #log in as recipient
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/messages/dm/')
        self.assertEqual(len(response.data['results']), 1)
        rec = MessageRecipient.objects.filter(message=msg, recipient=self.data_collector).first()
        self.assertEqual(rec.read, False)
        self.assertEqual(rec.actionable, True)
        self.assertEqual(rec.completed, False)

        response = self.client.patch(f'/api/messages/dm/{msg.id}/read/') #mark as read

        response = self.client.patch(f'/api/messages/dm/{msg.id}/complete/') #mark as complete
        rec.refresh_from_db()
        self.assertEqual(rec.read, True)
        self.assertEqual(rec.completed, True)

        valid_reply = {
            'parent': msg.id,
            'body': 'I did the dew!'
        } #post a reply
        response = self.client.post('/api/messages/dm/', valid_reply, format='json')

        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/messages/dm/')
        self.assertEqual(len(response.data['results']), 1) #1 because replies do not show at top-level.

        #also sanity check, messages don't show up for others
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/messages/dm/')
        self.assertEqual(len(response.data['results']), 0)


        
    
