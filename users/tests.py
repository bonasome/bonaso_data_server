from django.test import TestCase
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from rest_framework import status

from organizations.models import Organization
User = get_user_model()

class JWTAuthTest(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org')
        self.user = User.objects.create_user(username='testuser', password='testpass123', role='admin')
        self.user.organization = self.org

        self.user_me = User.objects.create_user(username='testme', password='testpass123', role='meofficer')
        self.user_me.organization = self.org

        self.user_dc = User.objects.create_user(username='testdc', password='testpass123', role='data_collector')
        self.user_dc.organization = self.org

        self.user_no_org = User.objects.create_user(username='testnoorg', password='testpass', role='meofficer')
        self.inactive_user = User.objects.create_user(username='testinactiveuser', password='testpass123', role='admin')
        self.inactive_user.is_active = False
        self.inactive_user.save()

    def test_login(self):
        response =self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)
        token = response.cookies.get('access_token').value

    def test_failed_login(self):
        response =self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass12'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive(self):
        response = self.client.post('/api/users/request-token/', {
            'username': 'testinactiveuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_access_protected_view(self):
        response = self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        token = response.cookies.get('access_token').value

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_refresh_token(self):
        response = self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        refresh_token = response.cookies.get('refresh_token').value

        # Refresh the token
        response = self.client.post('/api/users/token/refresh/', {
            'refresh': refresh_token
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.cookies)

        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
    def test_logout(self):
        response = self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post('/api/users/logout/')
        self.assertEqual(response.status_code, 200)

        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, 401)

        response = self.client.post('/api/users/token/refresh/')
        self.assertEqual(response.status_code, 400)
    
    def test_apply_for_user(self):
        self.client.force_authenticate(user=self.user_me)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewuser',
            'password': 'testpass123',
            'email': 'test@user.com',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response =self.client.post('/api/users/request-token/', {
            'username': 'testnewuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.get('/api/manage/targets/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)
    
    def test_apply_for_user_no_org(self):
        self.client.force_authenticate(user=self.user_no_org)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewuser2',
            'password': 'testpass123',
            'email': 'test@user.com',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_apply_for_user_no_perm(self):
        self.client.force_authenticate(user=self.user_dc)
        response = self.client.post('/api/users/create-user/', {
            'username': 'testnewuser3',
            'password': 'testpass123',
            'email': 'test@user.com',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        