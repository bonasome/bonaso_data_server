from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from users.models import User
from profiles.models import FavoriteRespondent
from respondents.models import Respondent
from organizations.models import Organization



from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from datetime import datetime
from projects.models import Project, Client, Task, Target
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus
from organizations.models import Organization
from indicators.models import Indicator, IndicatorSubcategory
from datetime import date
User = get_user_model()

class ProfileViewSetTest(APITestCase):
    def setUp(self):
        self.today = date.today().isoformat()
        
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='officer', password='testpass', role='manager')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.child_data_collector = User.objects.create_user(username='data_collector2', password='testpass', role='data_collector')
        self.loser = User.objects.create_user(username='i_wish_i_was_in_that_org', password='testpass', role='data_collector')

        self.org = Organization.objects.create(name='Test Org')
        self.child_org = Organization.objects.create(name='Child Org')
        self.other_org = Organization.objects.create(name='Loser Org')

        self.admin.organization = self.org
        self.admin.save()

        self.manager.organization = self.org
        self.manager.save()

        self.data_collector.organization = self.org
        self.data_collector.save()

        self.child_data_collector.organization = self.child_org
        self.child_data_collector.save()

        self.loser.organization = self.other_org
        self.loser.save()

    def test_admin_can_see_all_users(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 5)

    def test_officer_can_see_own_and_child_org_users(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    def test_regular_user_can_only_see_self(self):
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['username'], 'data_collector')

    def test_cannot_delete_user(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/profiles/users/{self.data_collector.id}/')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data['detail'], "Deleting users is not allowed. Mark them as inactive instead.")


class FavoriteRespondentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass123')
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
