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
        '''
        Test user login. Make sure the data is all sent.
        '''
        response =self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)
        token = response.cookies.get('access_token').value

    def test_failed_login(self):
        '''
        Sanity check to make sure wrong information doesn't grant access.
        '''
        response =self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass12'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive(self):
        '''
        Make sure inactive users do not get auth.
        '''
        response = self.client.post('/api/users/request-token/', {
            'username': 'testinactiveuser',
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_access_protected_view(self):
        '''
        Make sure rolerestriected viewset allows access to valid users. 
        '''
        response = self.client.post('/api/users/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        })
        token = response.cookies.get('access_token').value

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_refresh_token(self):
        '''
        Test that the refresh token works.
        '''
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
        '''
        Test that logging out works and deletes token information. 
        '''
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

    def test_mobile_login(self):
        '''
        Test that mobile login method also works and that the payload sends token data. 
        '''
        response = self.client.post('/api/users/mobile/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Parse the response JSON
        data = response.json()

        # Assert that the tokens are returned
        self.assertIn('access', data)
        self.assertIn('refresh', data)
    
    def test_refresh_mobile_token(self):
        '''
        Same for refresh views.
        '''
        # Step 1: Log in to get the refresh token
        response = self.client.post('/api/users/mobile/request-token/', {
            'username': 'testuser',
            'password': 'testpass123'
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        tokens = response.json()
        refresh_token = tokens.get('refresh')
        self.assertIsNotNone(refresh_token)

        # Step 2: Use refresh token to get a new access token
        response = self.client.post('/api/users/mobile-token/refresh/', {
            'refresh': refresh_token
        }, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        new_access_token = response.json().get('access')
        self.assertIsNotNone(new_access_token)

        # Step 3: Use new access token to call protected endpoint
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access_token}')
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)