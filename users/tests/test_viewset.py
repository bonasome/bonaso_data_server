from django.test import TestCase
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from rest_framework import status

from organizations.models import Organization
from respondents.models import Respondent
User = get_user_model()

class RestrictedViewSetTest(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Test Org')
        self.admin = User.objects.create_user(username='testuser', password='testpass123', role='admin')
        self.admin.organization = self.org


        self.view_only = User.objects.create_user(username='view', password='testpass123', role='view_only')
        self.view_only.organization = self.org

        self.user_no_org = User.objects.create_user(username='testnoorg', password='testpass', role='meofficer')
        
        self.user_no_role = User.objects.create_user(username='no_role', password='testpass123')
        self.user_no_role.organization = self.org
        
        self.inactive_user = User.objects.create_user(username='testinactiveuser', password='testpass123', role='admin')
        self.inactive_user.is_active = False
        self.inactive_user.save()

        self.respondent_anon= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

    #try this with a few different viewsets that inherit from this class
    def test_valid_user(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_view_only(self):
        self.client.force_authenticate(user=self.view_only)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_no_org(self):
        self.client.force_authenticate(user=self.user_no_org)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_no_role(self):
        self.client.force_authenticate(user=self.user_no_role)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_inactive(self):
        self.client.force_authenticate(user=self.inactive_user)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)




