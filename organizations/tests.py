from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from organizations.models import Organization
from projects.models import Project
from indicators.models import Indicator, IndicatorSubcategory

User = get_user_model()
class OrganizationViewSetTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')
        self.client.force_authenticate(user=self.admin)
        self.org = Organization.objects.create(name='Test Org')
        self.org2 = Organization.objects.create(name='Test Org 2')
        self.org3 = Organization.objects.create(name='Test Org 3', parent_organization=self.org)

        self.admin.organization = self.org
        self.user2.organization = self.org
        
        self.project = Project.objects.create(
            name='Beta Project',
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.org])

    def test_anon(self):
        self.client.logout()
        response = self.client.get('/api/organizations/')
        self.assertEqual(response.status_code, 401)

    def test_view_only(self):
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/organizations/')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(response.data['results']), 0)

    def test_organization_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/organizations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_not_admin_list(self):
        self.client.force_authenticate(user=self.user2)
        response = self.client.get('/api/organizations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_search_organization(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/organizations/?search=2')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_organization_filter_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/organizations/?project={self.project.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_organization_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/organizations/{self.org.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.org.id)
    
    def test_organization_create_view(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Test org 4',
        }
        response = self.client.post('/api/organizations/', valid_payload, format='json')
        if response.status_code != 201:
            print(response.status_code)
            print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_child_create_valid(self):
        self.client.force_authenticate(user=self.user2)
        valid_payload = {
            'name': 'Test org 5',
            'parent_organization_id': self.org.id
        }
        response = self.client.post('/api/organizations/', valid_payload, format='json')
        if response.status_code != 201:
            print(response.status_code)
            print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_child_create_invalid(self):
        self.client.force_authenticate(user=self.user2)
        valid_payload = {
            'name': 'Test org 6',
        }
        response = self.client.post('/api/organizations/', valid_payload, format='json')
        if response.status_code != 403:
            print(response.status_code)
            print(response.data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST  )



