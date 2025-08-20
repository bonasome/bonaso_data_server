from django.test import TestCase
from django.contrib.auth import get_user_model

from rest_framework.test import APITestCase
from rest_framework import status



from organizations.models import Organization
from projects.models import Client

User = get_user_model()

class UserCreationTest(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org')
        
        self.other_org = Organization.objects.create(name='Other Org')

        self.admin = User.objects.create_user(username='testuser', password='testpass123', role='admin')
        self.admin.organization = self.org

        self.officer = User.objects.create_user(username='testme', password='testpass123', role='meofficer')
        self.officer.organization = self.org

        self.data_collector = User.objects.create_user(username='testdc', password='testpass123', role='data_collector')
        self.data_collector.organization = self.org
        self.client_user = User.objects.create_user(username='client', password='testpass123', role='client')

        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.client_user.client_organization = self.client_obj

        self.user_no_org = User.objects.create_user(username='testnoorg', password='testpass', role='meofficer')
        self.inactive_user = User.objects.create_user(username='testinactiveuser', password='testpass123', role='admin')
        self.inactive_user.is_active = False
        self.inactive_user.save()
    
    def test_apply_for_user(self):
        '''
        Higher roles should be able to create users like the below.
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewuser',
            'password': 'testpass123',
            'email': 'test@user.com',
            'first_name': 'James',
            'last_name': 'LeBron',
            'organization_id': self.org.id,
            'role': 'meofficer',
        })
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(username='testnewuser')
        self.assertEqual(new_user.is_active, False)
    
    def test_apply_for_user_wrong_org(self):
        '''
        But they should only be able to do this for related orgs
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewuser',
            'password': 'testpass123',
            'email': 'test@user.com',
            'first_name': 'James',
            'last_name': 'LeBron',
            'organization_id': self.other_org.id,
            'role': 'manager',
        })
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_client(self):
        '''
        Admins should be able to create client users like this.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewclient',
            'password': 'testpass123',
            'email': 'test@user.com',
            'first_name': 'James',
            'last_name': 'LeBron',
            'role': 'client',
            'client_id': self.client_obj.id,
        })
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_client_client(self):
        '''
        Admins should be able to create client users like this.
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewclient',
            'password': 'testpass123',
            'email': 'test@user.com',
            'first_name': 'James',
            'last_name': 'LeBron',
            'role': 'client',
            'client_id': self.client_obj.id,
        })
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_apply_for_user_no_org(self):
        '''
        If a user has no role they are not allowed to do this.
        '''
        self.client.force_authenticate(user=self.user_no_org)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewuser2',
            'password': 'testpass123',
            'email': 'test@user.com',
            'role': 'admin',
        })
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_apply_for_user_no_perm(self):
        '''
        Same if they have insufficient role privlleges.
        '''
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewuser3',
            'password': 'testpass123',
            'email': 'test@user.com',
            'role': 'admin',
            'organization_id': self.org.id,
        })
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)