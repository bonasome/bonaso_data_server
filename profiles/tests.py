from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from datetime import date
from profiles.models import FavoriteObject
from projects.models import Project, ProjectOrganization
from organizations.models import Organization
from projects.models import Project, Client
from respondents.models import Respondent, Interaction
User = get_user_model()

class ProfileViewSetTest(APITestCase):
    '''
    Basic test that the profile viewset works and only returns profiles that a user should be seeing:
        -Admins: all
        -Higher Roles: Orgs+child orgs
        -Everyone else: themselves
    '''
    def setUp(self):
        self.parent = Organization.objects.create(name='Parent Org')
        self.child = Organization.objects.create(name='Child Org')
        self.wrong = Organization.objects.create(name='Wrong Org')

        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.parent)
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer', organization=self.parent)
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager', organization=self.parent)
        self.mechild = User.objects.create_user(username='mechild', password='testpass', role='meofficer', organization=self.child)
        self.wrong_org = User.objects.create_user(username='wrong_org', password='testpass', role='meofficer', organization=self.wrong)
        self.data_collector = User.objects.create_user(username='dc', password='testpass', role='data_collector', organization=self.parent)

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)

        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent, self.wrong, self.child])

        
        child_link = ProjectOrganization.objects.filter(organization=self.child).first()
        child_link.parent_organization = self.parent
        child_link.save()

        '''
        This is all to test the feed
        '''
        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
            created_by=self.admin
        )

    def test_admin_see_all(self):
        '''
        Admins should be able to see all users.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 6)
    
    def test_officer_see_org(self):
        '''
        Officers should see their org + children
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 5)
    
    def test_dc_see_self(self):
        '''
        Lower roles can only see self
        '''
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/profiles/users/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)

    def test_dc_patch_self(self):
        '''
        Lower roles can patch self
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'first_name': 'Goolius',
        }
        response = self.client.patch(f'/api/profiles/users/{self.data_collector.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.data_collector.refresh_from_db()
        self.assertEqual(self.data_collector.first_name, 'Goolius')
    
    def test_me_officer_patch_child(self):
        '''
        Officers can patch their subordinates.
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'first_name': 'Goolius',
        }
        response = self.client.patch(f'/api/profiles/users/{self.mechild.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, 200)
        self.mechild.refresh_from_db()
        self.assertEqual(self.mechild.first_name, 'Goolius')
    
    def test_me_officer_cannot_patch_other(self):
        '''
        But not others
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'first_name': 'Goolius',
        }
        response = self.client.patch(f'/api/profiles/users/{self.wrong_org.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, 404)

    def test_activity(self):
        '''
        Quick test to see if feed returns things
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/profiles/users/{self.admin.id}/activity/')
        print(response.json())
        self.assertEqual(response.status_code, 200)

class FavoriteTests(APITestCase):
    '''
    Test to make sure the favorite system works. Test favoriting, unfavoriting and getting favoties
    '''
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123', role='data_collector')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass123', role='data_collector')
        self.org = Organization.objects.create(name='Test Org')

        self.user.organization = self.org
        self.user2.organization = self.org
        self.respondent = Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

    def test_favorite_unfavorite_Respondent(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post('/api/profiles/users/favorite/', 
            {'model': 'respondents.respondent', 'id': self.respondent.id}
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.get('/api/profiles/users/get-favorites/')
        print(response.json())
        self.assertEqual(len(response.data), 1)

        response = self.client.delete('/api/profiles/users/unfavorite/', 
            {'model': 'respondents.respondent', 'id': self.respondent.id}
        )
        self.assertEqual(FavoriteObject.objects.filter(user=self.user).count(), 0)
