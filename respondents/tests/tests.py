from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from respondents.models import Respondent, Interaction, KeyPopulation
from projects.models import Project, Client, Task
from organizations.models import Organization
from indicators.models import Indicator, IndicatorSubcategory
import uuid
User = get_user_model()
from datetime import datetime, date


class RespondentViewSetTest(APITestCase):
    def setUp(self):
        #set up users, organizations, and respondents
        self.today = date.today().isoformat()
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.me_officer = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.no_org = User.objects.create_user(username='no_org', password='testpass', role='data_collector')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')
        
        self.org = Organization.objects.create(name='Test Org')
        
        self.admin.organization = self.org
        self.me_officer.organization = self.org
        self.data_collector.organization = self.org

        self.respondent = Respondent.objects.create(
            is_anonymous=True,
            uuid=str(uuid.uuid4()),
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        self.respondent2 = Respondent.objects.create(
            is_anonymous=True,
            uuid=str(uuid.uuid4()),
            age_range=Respondent.AgeRanges.ET_24,
            village='Coolplace',
            citizenship = 'test',
            district= Respondent.District.CENTRAL,
            sex = Respondent.Sex.MALE,
        )
    
    def test_anon(self):
        #test to make sure anonymous users cannot view or create records
        self.client.logout()
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, 401)
        response = self.client.post('/api/record/respondents/')
        self.assertEqual(response.status_code, 401)

    def test_view_only(self):
        #test to make sure view only users cannot view or create records
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

        response = self.client.post('/api/record/respondents/')
        self.assertEqual(response.status_code, 403)
    
    def test_no_org(self):
        #test to make sure users who do not belong to an org cannot view or post data
        self.client.force_authenticate(user=self.no_org)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

        response = self.client.post('/api/record/respondents/')
        self.assertEqual(response.status_code, 403)

    def test_respondent_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_search_respondents(self):
        #make sure search (sample village) works
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/', {'search': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['village'], 'Testingplace')

    def test_filter_respondents(self):
        #make sure search (sample village) works
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/', {'search': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['village'], 'Testingplace')

    def test_respondent_detail_view(self):
        #make sure detail views return the right info
        self.client.force_authenticate(user=self.admin)
        url = f'/api/record/respondents/{self.respondent2.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.respondent2.id)

    def test_create_respondent(self):
        #test creating both anonymous and full respondent profiles
        self.client.force_authenticate(user=self.data_collector)
        uuidVal = str(uuid.uuid4())
        valid_payload_anon = {
            'is_anonymous':True,
            'age_range': Respondent.AgeRanges.ET_24,
            'village': 'Place', 
            'citizenship': 'Test',
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
        }
        valid_payload_full = {
            'is_anonymous':False,
            'id_no': '1234',
            'first_name': 'Test',
            'last_name': 'Testerson',
            'dob': '2000-01-01',
            'ward': 'Here',
            'village': 'Place', 
            'citizenship': 'Test',
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
        }
        response = self.client.post('/api/record/respondents/', valid_payload_anon, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent = Respondent.objects.get(village='Place')
        self.assertEqual(respondent.village,'Place')
        self.assertEqual(respondent.created_by, self.data_collector)

        response = self.client.post('/api/record/respondents/', valid_payload_full, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent = Respondent.objects.get(village='Place')
        self.assertEqual(respondent.id_no,'id_no')
        self.assertEqual(respondent.created_by, self.data_collector)

    def test_patch_respondent(self):
        #test patching
        valid_patch = {
            'ward': 'There'
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent2.id}/', valid_patch, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent2.refresh_from_db()
        self.assertEqual(self.respondent2.ward, 'There')

class SensitiveInfoViewSetTest(APITestCase):
    def setUp(self):
        #set up users, organizations, and respondents
        self.today = date.today().isoformat()
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.me_officer = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.no_org = User.objects.create_user(username='data_collector2', password='testpass', role='data_collector')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')
        
        self.org = Organization.objects.create(name='Test Org')
        
        self.admin.organization = self.org
        self.me_officer.organization = self.org
        self.data_collector.organization = self.org

        self.respondent = Respondent.objects.create(
            is_anonymous=True,
            uuid=str(uuid.uuid4()),
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
    def test_sensative_info_create(self):
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'is_pregnant': True,
            'term_began': '2025-01-01',
            'term_ended': None,
            'hiv_status': True,
            'date_positive': '2023-02-05',
            'kp_status_names': ['MSM', 'FSW'],
            'disability_status_names': ['VI', 'PD'],
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent.refresh_from_db()
        self.assertEqual(self.respondent.kp_status.count(), 2)

from rest_framework.test import APITestCase
from rest_framework import status
from datetime import date
import uuid

class InteractionViewSetTest(APITestCase):
    def setUp(self):
        self.today = date.today()

        # Users and Orgs
        self.org = Organization.objects.create(name='Test Org')
        self.org2 = Organization.objects.create(name='Test Org2')
        self.wrong_org = Organization.objects.create(name='Wrong Org')

        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.org)
        self.me_officer = User.objects.create_user(username='me', password='testpass', role='meofficer', organization=self.org)
        self.data_collector = User.objects.create_user(username='dc', password='testpass', role='data_collector', organization=self.org)
        self.no_org = User.objects.create_user(username='noorg', password='testpass', role='data_collector')
        self.view_user = User.objects.create_user(username='viewer', password='testpass', role='view_only')
        self.wrong_org_user = User.objects.create_user(username='wrongorg', password='testpass', role='manager', organization=self.wrong_org)

        # Project and Indicators
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.project = Project.objects.create(
            name='Gamma Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.org, self.org2])

        self.ind = Indicator.objects.create(code='1', name='Test Ind')
        self.ind_parent = Indicator.objects.create(code='2', name='Parent Ind')
        self.ind_child = Indicator.objects.create(code='3', name='Child Ind', prerequisite=self.ind_parent)
        self.ind_number = Indicator.objects.create(code='4', name='Numeric Ind', require_numeric=True)
        self.ind_subcat_child = Indicator.objects.create(code='5', name='Subcat Child', prerequisite=self.ind)

        self.project.indicators.set([self.ind, self.ind_parent, self.ind_child, self.ind_number, self.ind_subcat_child])

        self.category = IndicatorSubcategory.objects.create(name='Cat 1')
        self.category2 = IndicatorSubcategory.objects.create(name='Cat 2')

        # Tasks
        self.task = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind)
        self.task2 = Task.objects.create(project=self.project, organization=self.org, indicator=self.ind)
        self.task_number = Task.objects.create(project=self.project, organization=self.org, indicator=self.ind_number)
        self.task_parent = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind_parent)
        self.task_child = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind_child)
        self.task_subcat_child = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind_subcat_child)

        self.task.indicator.subcategories.add(self.category, self.category2)
        self.task_subcat_child.indicator.subcategories.add(self.category, self.category2)

        # Respondents
        self.respondent = Respondent.objects.create(
            is_anonymous=True,
            uuid=uuid.uuid4(),
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district=Respondent.District.CENTRAL,
            citizenship='test',
            sex=Respondent.Sex.FEMALE,
        )
        self.respondent2 = Respondent.objects.create(
            is_anonymous=True,
            uuid=uuid.uuid4(),
            age_range=Respondent.AgeRanges.ET_24,
            village='Coolplace',
            citizenship='test',
            district=Respondent.District.CENTRAL,
            sex=Respondent.Sex.MALE,
        )

        # Interactions
        self.interaction = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, task=self.task, created_by=self.admin)
        self.interaction.subcategories.set([self.category])
        self.interaction2 = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent2, task=self.task2)

    def test_anon(self):
        self.client.logout()
        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, 401)

    def test_view_only(self):
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

    def test_interaction_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 2)

    def test_interaction_filter(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/record/interactions/?task={self.task.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)

    def test_interaction_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/record/interactions/{self.interaction.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['id'], self.interaction.id)

    def test_create_interaction(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'respondent': self.respondent2.id,
            'task': self.task.id,
            'subcategories': [self.category.id, self.category2.id]
        }, format='json')
        self.assertEqual(response.status_code, 201)

    def test_create_interaction_with_number(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_number.id,
            'numeric_component': 10
        }, format='json')
        self.assertEqual(response.status_code, 201)

    def test_bulk_create(self):
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.post('/api/record/interactions/bulk_create/', {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'tasks': [
                {'task': self.task.id},
                {'task': self.task_number.id, 'numeric_component': 10},
                {'task': self.task.id, 'subcategory_names': ['Cat 1', 'Cat 2']}
            ]
        }, format='json')
        self.assertEqual(response.status_code, 201)

    def test_create_interaction_with_number_invalid(self):
        self.client.force_authenticate(user=self.admin)
        bad = {'interaction_date': date(2025, 6, 1), 'respondent': self.respondent2.id, 'task': self.task_number.id, 'numeric_component': 'nope'}
        response = self.client.post('/api/record/interactions/', bad, format='json')
        self.assertEqual(response.status_code, 400)

        missing = {'interaction_date': date(2025, 6, 1), 'respondent': self.respondent.id, 'task': self.task_number.id}
        response = self.client.post('/api/record/interactions/', missing, format='json')
        self.assertEqual(response.status_code, 400)

    def test_create_interaction_with_prereq(self):
        self.client.force_authenticate(user=self.admin)
        parent = {'interaction_date': date(2025, 6, 1), 'respondent': self.respondent2.id, 'task': self.task_parent.id}
        response = self.client.post('/api/record/interactions/', parent, format='json')
        self.assertEqual(response.status_code, 201)

        child = {'interaction_date': date(2025, 6, 1), 'respondent': self.respondent2.id, 'task': self.task_child.id}
        response = self.client.post('/api/record/interactions/', child, format='json')
        self.assertEqual(response.status_code, 201)

    def test_create_interaction_with_invalid_prereq(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_child.id
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_create_interaction_no_subcat(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': self.task.id
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_patch_interaction_wrong_user(self):
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/interactions/{self.interaction.id}/', {
            'interaction_date': self.today
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_patch_interaction_wrong_org(self):
        self.client.force_authenticate(user=self.wrong_org_user)
        response = self.client.patch(f'/api/record/interactions/{self.interaction.id}/', {
            'interaction_date': self.today
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_create_interaction_matched_subcat(self):
        self.client.force_authenticate(user=self.admin)
        for names in [['Cat 1', 'Cat 2'], ['Cat 1']]:
            response = self.client.post('/api/record/interactions/', {
                'interaction_date': self.today,
                'respondent': self.respondent2.id,
                'task': self.task.id,
                'subcategories': names
            }, format='json')
            self.assertEqual(response.status_code, 201)

    def test_create_interaction_mismatched_subcat(self):
        self.client.force_authenticate(user=self.admin)
        ind1 = Indicator.objects.create(code='10', name='ParentSubcat')
        ind2 = Indicator.objects.create(code='11', name='ChildSubcat', prerequisite=ind1)
        ind1.subcategories.set([self.category, self.category2])
        ind2.subcategories.set([self.category, self.category2])

        task1 = Task.objects.create(project=self.project, organization=self.org2, indicator=ind1)
        task2 = Task.objects.create(project=self.project, organization=self.org2, indicator=ind2)

        self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': task1.id,
            'subcategory_names': ['Cat 1']
        }, format='json')

        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': task2.id,
            'subcategory_names': ['Cat 1', 'Cat 2']
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_flag(self):
        self.client.force_authenticate(user=self.admin)
        self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 5),
            'respondent': self.respondent2.id,
            'task': self.task_parent.id
        }, format='json')

        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 7),
            'respondent': self.respondent2.id,
            'task': self.task_parent.id
        }, format='json')

        self.assertEqual(response.status_code, 201)
        interaction = Interaction.objects.get(interaction_date=date(2025, 6, 7), task=self.task_parent, respondent=self.respondent2)
        self.assertTrue(interaction.flagged)