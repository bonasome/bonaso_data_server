from django.test import TestCase

from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from users.models import User
from profiles.models import FavoriteRespondent
from respondents.models import Respondent

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
