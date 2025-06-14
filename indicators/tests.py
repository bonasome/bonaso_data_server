from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from organizations.models import Organization
from projects.models import Project
from indicators.models import Indicator, IndicatorSubcategory

User = get_user_model()
class IndicatorViewSetTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')
        self.client.force_authenticate(user=self.admin)
        self.org = Organization.objects.create(name='Test Org')

        self.admin.organization = self.org

        self.ind = Indicator.objects.create(code='1', name='Test Ind')
        self.ind2 = Indicator.objects.create(code='2', name='Test Ind 2')

        self.project = Project.objects.create(
            name='Beta Project',
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.project.indicators.set([self.ind])

    def test_anon(self):
        self.client.logout()
        response = self.client.get('/api/indicators/')
        self.assertEqual(response.status_code, 401)

    def test_view_only(self):
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/indicators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

    def test_indicator_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/indicators/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_search_indicators(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/indicators/?search=2')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['code'], '2')
    
    def test_indicator_filter_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/indicators/?project={self.project.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_indicator_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/indicators/{self.ind.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.ind.id)
    
    def test_indicator_create_view(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
            'prerequisite_id': self.ind2.id,
        }
        response = self.client.post('/api/indicators/', valid_payload, format='json')
        if response.status_code != 201:
            print(response.status_code)
            print(response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        indicator = Indicator.objects.get(code='3')
        self.assertEqual(indicator.prerequisite.id, self.ind2.id)

        valid_payload2 = {
            'name': 'Ind 3',
            'code': '4',
            'subcategory_names': ['1', '2'],
        }
        response = self.client.post('/api/indicators/', valid_payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        indicator = Indicator.objects.get(code='4')
        self.assertEqual(indicator.subcategories.count(), 2)
    
    def test_no_perm_create(self):
        self.client.force_authenticate(user=self.user2)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
            'prerequisite': self.ind2.id,
        }
        response = self.client.post('/api/indicators/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


