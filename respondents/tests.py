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
        self.today = date.today().isoformat()
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')
        self.org = Organization.objects.create(name='Test Org')
        self.org2 = Organization.objects.create(name='Test Org 2')
        
        self.admin.organization = self.org
        self.user2.organization = self.org2

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

        self.project.indicators.set([self.ind])

        self.task = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind)
        self.task2 = Task.objects.create(project=self.project, organization=self.org, indicator=self.ind)

        self.category = IndicatorSubcategory.objects.create(indicator=self.ind, name='Cat 1')
        self.category2 = IndicatorSubcategory.objects.create(indicator=self.ind, name='Cat 2')

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
        self.fsw = KeyPopulation.objects.create(name=KeyPopulation.KeyPopulations.FSW)
        self.msm = KeyPopulation.objects.create(name=KeyPopulation.KeyPopulations.MSM)
        self.respondent2.kp_status.set([self.fsw, self.msm])
    
    def test_anon(self):
        self.client.logout()
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, 401)

    def test_view_only(self):
        self.client.force_authenticate(user=self.view_user)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 0)

    def test_respondent_list_view(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_search_respondents(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/', {'search': 'Test'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['village'], 'Testingplace')

    def test_project_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/record/respondents/{self.respondent2.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.respondent2.id)


    def test_create_respondent(self):
        self.client.force_authenticate(user=self.admin)
        uuidVal = str(uuid.uuid4())
        valid_payload = {
            'is_anonymous':True,
            'uuid': uuidVal,
            'age_range': Respondent.AgeRanges.ET_24,
            'village': 'Place', 
            'citizenship': 'Test',
            'is_pregnant': True,
            'hiv_positive': True,
            'positive_since': '2012-12-22',
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
            'kp_status_id': [self.fsw.id, self.msm.id]
        }
        response = self.client.post('/api/record/respondents/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent = Respondent.objects.get(village='Place')
        hiv = respondent.hivstatus_set.first()
        pregnant = respondent.pregnancy_set.first()
        self.assertEqual(pregnant.term_began, date.today())
        self.assertEqual(pregnant.is_pregnant, True)
        self.assertEqual(hiv.hiv_positive, True)
        self.assertEqual(respondent.kp_status.count(), 2)
        self.assertEqual(hiv.date_positive, date.fromisoformat('2012-12-22'))

    def test_patch_respondent(self):
        valid_patch = {
            'kp_status_id': [self.fsw.id],
        }
        self.client.force_authenticate(user=self.admin)
        response = self.client.patch(f'/api/record/respondents/{self.respondent2.id}/', valid_patch, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.respondent2.refresh_from_db()
        self.assertEqual(self.respondent2.kp_status.count(), 1)

class InteractionViewSetTest(APITestCase):
    def setUp(self):
        self.today = date.today().isoformat()
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.user2 = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        self.org = Organization.objects.create(name='Test Org')
        self.org2 = Organization.objects.create(name='Test Org 2')
        
        self.admin.organization = self.org
        self.user2.organization = self.org2

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
        self.ind_parent = Indicator.objects.create(code='2', name='Test Ind Prereq')
        self.ind_child = Indicator.objects.create(code='3', name='Test Ind Prereq Child', prerequisite=self.ind_parent)
        self.project.indicators.set([self.ind, self.ind_parent, self.ind_child])
        self.ind_number = Indicator.objects.create(code='4', name='Test Numeric', require_numeric=True)

        self.ind_subcat_child = Indicator.objects.create(code='5', name='Test Subcat Child', prerequisite=self.ind)

        self.task = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind)
        self.task2 = Task.objects.create(project=self.project, organization=self.org, indicator=self.ind)
        self.task_number = Task.objects.create(project=self.project, organization=self.org, indicator=self.ind_number)
        
        self.task_parent = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind_parent)
        self.task_child = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind_child)
        
        self.task_subcat_child = Task.objects.create(project=self.project, organization=self.org2, indicator=self.ind_subcat_child)

        self.category = IndicatorSubcategory.objects.create(name='Cat 1')
        self.category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        self.task.indicator.subcategories.add(self.category, self.category2)
        self.task_subcat_child.indicator.subcategories.add(self.category, self.category2)
        self.respondent = Respondent.objects.create(
            is_anonymous=True,
            uuid=uuid.uuid4(),
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        self.respondent2 = Respondent.objects.create(
            is_anonymous=True,
            uuid=uuid.uuid4(),
            age_range=Respondent.AgeRanges.ET_24,
            village='Coolplace',
            citizenship = 'test',
            district= Respondent.District.CENTRAL,
            sex = Respondent.Sex.MALE,
        )

        self.interaction = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, task=self.task)
        self.interaction2 = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent2, task=self.task2)
        self.interaction.subcategories.set([self.category.id])
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
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_interaction_filter(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/record/interactions/?task={self.task.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

    def test_interaction_detail_view(self):
        self.client.force_authenticate(user=self.admin)
        url = f'/api/record/interactions/{self.interaction.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.interaction.id)


    def test_create_interaction(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'interaction_date': self.today,
            'respondent': self.respondent2.id,
            'task': self.task.id,
            'subcategories': [self.category.id, self.category2.id]
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        interaction = Interaction.objects.get(respondent=self.respondent2, task=self.task.id)
        self.assertEqual(interaction.interaction_date, date.today())
        self.assertEqual(interaction.subcategories.count(), 2)
    
    def test_create_interaction_with_number(self):
        self.client.force_authenticate(user=self.admin)

        valid_payload = {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_number.id,
            'numeric_component': 10
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_interaction_with_number_invalid(self):
        self.client.force_authenticate(user=self.admin)

        invalid_payload= {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_number.id,
            'numeric_component': 'what?'
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload2= {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent.id,
            'task': self.task_number.id,
        }
        response = self.client.post('/api/record/interactions/', invalid_payload2, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_create_interaction_with_prereq(self):
        self.client.force_authenticate(user=self.admin)

        valid_payload_parent = {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_parent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload_parent, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        valid_payload_child = {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_child.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload_child, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        if response.status_code != 201:
            print(response.status_code)
            print(response.data)
    
    def test_create_interaction_with_invalid_prereq(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload_child_no_parent = {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_child.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload_child_no_parent, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_interaction_invalid_dates(self):
        self.client.force_authenticate(user=self.admin)

        valid_payload_parent = {
            'interaction_date': date(2025, 6, 5),
            'respondent': self.respondent2.id,
            'task': self.task_parent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload_parent, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        valid_payload_child = {
            'interaction_date': date(2025, 6, 1),
            'respondent': self.respondent2.id,
            'task': self.task_child.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload_child, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_create_interaction_no_subcat(self):
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': self.task.id,
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    

    def test_create_interaction_matched_subcat(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'interaction_date': self.today,
            'respondent': self.respondent2.id,
            'task': self.task.id,
            'subcategories': [self.category.id, self.category2.id]
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        valid_payload = {
            'interaction_date': self.today,
            'respondent': self.respondent2.id,
            'task': self.task.id,
            'subcategories': [self.category.id]
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    
    def test_create_interaction_mismatched_subcat(self):
        self.client.force_authenticate(user=self.admin)
        ind1 = Indicator.objects.create(code='10', name='test subcat parent')
        ind1.subcategories.set([self.category, self.category2])
        ind2 = Indicator.objects.create(code='11', name='test subcat child', prerequisite=ind1)
        ind2.subcategories.set([self.category, self.category2])

        task1 = Task.objects.create(project=self.project, organization=self.org2, indicator=ind1)
        task2 = Task.objects.create(project=self.project, organization=self.org2, indicator=ind2)
        valid_payload = {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': task1.id,
            'subcategories': [self.category.id],
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        invalid_payload = {
            'interaction_date': self.today,
            'respondent': self.respondent.id,
            'task': task2.id,
            'subcategories': [self.category.id, self.category2.id],
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)