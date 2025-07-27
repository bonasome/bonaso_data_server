from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from organizations.models import Organization
from projects.models import Project, ProjectOrganization
from indicators.models import Indicator, IndicatorSubcategory

User = get_user_model()
class OrganizationViewSetTest(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.officer = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.data_collector = User.objects.create(username='dc', password='testpass', role='data_collector')
        self.client.force_authenticate(user=self.admin)
        self.parent_org = Organization.objects.create(name='Test Org')
        self.child_org = Organization.objects.create(name='Test Org 2')
        self.other_org = Organization.objects.create(name='Test Org 3')

        self.admin.organization = self.parent_org
        self.officer.organization = self.parent_org
        self.data_collector.organization = self.parent_org

        self.project = Project.objects.create(
            name='Beta Project',
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent_org, self.child_org])
        
        child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        child_link.parent_organization = self.parent_org
        child_link.save()

    def test_organization_list_view(self):
        '''
        Test admins can see all.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/organizations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_not_admin_list(self):
        '''
        Higher roles can see themselves and their children.
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.get('/api/organizations/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_organization_create_view(self):
        '''
        Admins/higher roles can create orgs
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Test org 4',
        }
        response = self.client.post('/api/organizations/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_dc_no_create(self):
        '''
        Not lower roles
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'name': 'Test org 4',
        }
        response = self.client.post('/api/organizations/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_duplicate_names(self):
        '''
        Prevent duplicate names for clarity.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Test Org',
        }
        response = self.client.post('/api/organizations/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    



