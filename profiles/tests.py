from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from profiles.models import FavoriteProject, FavoriteRespondent, FavoriteTask
from organizations.models import Organization
from projects.models import Project, Client
from indicators.models import Indicator, IndicatorSubcategory
from respondents.models import Respondent
User = get_user_model()

class TestProfileViewSet(APITestCase):
    def setUp(self):
        self.parent = Organization.objects.create(name='Parent Org')
        self.child = Organization.objects.create(name='Child Org', parent_organization=self.parent)
        self.wrong = Organization.objects.create(name='Wrong Org')

        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.parent)
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer', organization=self.parent)
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager', organization=self.parent)
        self.mechild = User.objects.create_user(username='mechild', password='testpass', role='meofficer', organization=self.child)
        self.wrong_org = User.objects.create_user(username='wrong_org', password='testpass', role='meofficer', organization=self.wrong)
        self.data_collector = User.objects.create_user(username='dc', password='testpass', role='data_collector', organization=self.parent)


    def test_admin_see_all(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 6)
    
    def test_officer_see_org(self):
        self.client.force_authenticate(user=self.officer)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 5)
    
    def test_dc_see_self(self):
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
    

    def dc_patch_self(self):
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'first_name': 'Goolius',
        }
        response = self.client.patch(f'/api/profiles/users/{self.data_collector.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.data_collector.refresh_from_db()
        self.assertEqual(self.data_collector.first_name, 'Goolius')
    
    def me_officer_patch_child(self):
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'first_name': 'Goolius',
        }
        response = self.client.patch(f'/api/profiles/users/{self.mechild.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.mechild.refresh_from_db()
        self.assertEqual(self.mechild.first_name, 'Goolius')
    
    def me_officer_cannot_patch_other(self):
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'first_name': 'Goolius',
        }
        response = self.client.patch(f'/api/profiles/users/{self.wrong_org.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, 404)


#at some point we should maybe write some tests for other favorites, but this is lower stakes
class FavoriteRespondentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123', role='data_collector')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass123', role='data_collector')
        self.org = Organization.objects.create(name='Test Org')

        self.user.organization = self.org
        self.user2.organization = self.org
        self.respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

    def test_favorite_Respondent(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/profiles/favorite-respondents/', {'respondent_id': self.respondent.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FavoriteRespondent.objects.count(), 1)
        self.assertEqual(FavoriteRespondent.objects.first().user, self.user)

    def test_unfavorite_Respondent(self):
        self.client.force_authenticate(user=self.user)
        favorite = FavoriteRespondent.objects.create(user=self.user, respondent=self.respondent)
        url = f'/api/profiles/favorite-respondents/{favorite.pk}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(FavoriteRespondent.objects.count(), 0)
    
    def test_malicious_unfavorite_Respondent(self):
        self.client.force_authenticate(user=self.user2)
        favorite = FavoriteRespondent.objects.create(user=self.user, respondent=self.respondent)
        url = f'/api/profiles/favorite-respondents/{favorite.pk}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
