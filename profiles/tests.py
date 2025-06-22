from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from users.models import User
from profiles.models import FavoriteRespondent
from respondents.models import Respondent
from organizations.models import Organization



class ProfileViewSetTests(APITestCase):
    def setUp(self):
        # Setup org structure
        self.org_main = Organization.objects.create(name='Main Org')
        self.org_child = Organization.objects.create(name='Child Org', parent_organization=self.org_main)

        # Admin user
        self.admin = User.objects.create_user(username='admin', password='pass', role='admin')
        
        # ME Officer (has access to their org + children)
        self.officer = User.objects.create_user(username='officer', password='pass', role='meofficer', organization=self.org_main)
        
        # Manager in a child org
        self.manager = User.objects.create_user(username='manager', password='pass', role='manager', organization=self.org_child)

        # Regular user
        self.user = User.objects.create_user(username='user', password='pass', role='staff', organization=self.org_child)

        self.url = reverse('user-list')  # adjust to your router name if not `user-list`

    def authenticate(self, user):
        self.client = APIClient()
        self.client.force_authenticate(user=user)

    def test_admin_can_see_all_users(self):
        self.authenticate(self.admin)
        response = self.client.get(self.url)
        usernames = [u['username'] for u in response.data]
        self.assertIn('user', usernames)
        self.assertIn('officer', usernames)
        self.assertIn('manager', usernames)

    def test_officer_can_see_own_and_child_org_users(self):
        self.authenticate(self.officer)
        response = self.client.get(self.url)
        usernames = [u['username'] for u in response.data]
        self.assertIn('officer', usernames)
        self.assertIn('manager', usernames)
        self.assertIn('user', usernames)  # child org
        self.assertNotIn('admin', usernames)

    def test_regular_user_can_only_see_self(self):
        self.authenticate(self.user)
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['username'], 'user')

    def test_cannot_delete_user(self):
        self.authenticate(self.admin)
        url = reverse('user-detail', kwargs={'pk': self.user.id})  # adjust name if not 'user-detail'
        response = self.client.delete(url)
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
