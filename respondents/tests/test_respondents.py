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

class RespondentViewSetTest(APITestCase):
    def setUp(self):
        self.today = date.today().isoformat()
        
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.officer = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
        self.org = Organization.objects.create(name='Test Org')
        
        self.admin.organization = self.org
        self.officer.organization = self.org
        self.data_collector.organization = self.org
        self.client_user.organization = self.org

        self.respondent_anon= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

        self.respondent_full = Respondent.objects.create(
            is_anonymous=False, 
            id_no= '1234567',
            first_name= 'Test',
            last_name= 'Testerson',
            dob= date(2000, 1, 1),
            ward= 'Here',
            village= 'ThePlace', 
            citizenship= 'Test',
            sex= Respondent.Sex.FEMALE,
            district= Respondent.District.CENTRAL,
        )

    def test_respondent_list_view(self):
        #make sure respondents list returns all respondents
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_respondent_client_list_view(self):
        #make sure respondents list returns all respondents
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_search_respondents(self):
        #make sure search (sample village) works (very important for the app)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/', {'search': 'Testerson'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['village'], 'ThePlace')

    def test_respondent_detail_view(self):
        #make sure detail views return the right info
        self.client.force_authenticate(user=self.admin)
        url = f'/api/record/respondents/{self.respondent_full.id}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.respondent_full.id)
    
    #all perms have this privelge, so test with the lowest level
    def test_create_respondent(self):
        #test creating both anonymous and full respondent_anonprofiles
        self.client.force_authenticate(user=self.data_collector)
        valid_payload_anon = {
            'is_anonymous':True,
            'age_range': Respondent.AgeRanges.ET_24,
            'village': 'Here', 
            'citizenship': 'Test',
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
        }

        response = self.client.post('/api/record/respondents/', valid_payload_anon, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent_anon= Respondent.objects.get(village='Here')
        self.assertEqual(respondent_anon.village,'Here')
        self.assertEqual(respondent_anon.created_by, self.data_collector)


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

        response = self.client.post('/api/record/respondents/', valid_payload_full, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent= Respondent.objects.get(village='Place')
        self.assertEqual(respondent.id_no,'1234')
        self.assertEqual(respondent.created_by, self.data_collector)


    def test_create_duplicate(self):
        self.client.force_authenticate(user=self.data_collector)
        valid_payload_full = {
            'is_anonymous':False,
            'id_no': '1234567',
            'first_name': 'Test',
            'last_name': 'Testerson',
            'dob': '2000-01-01',
            'ward': 'Here',
            'village': 'Place', 
            'citizenship': 'Test',
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
        }

        response = self.client.post('/api/record/respondents/', valid_payload_full, format='json')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('existing_id', response.data)
        self.assertEqual(int(response.data['existing_id']), self.respondent_full.id)

    def test_patch_respondent(self):
        #test basic patch operation
        valid_patch = {
            'ward': 'There'
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        self.assertEqual(self.respondent_full.ward, 'There')
        self.assertEqual(self.respondent_full.updated_by, self.data_collector)
    
    def test_switch_respondent_type(self):
        #test to make sure respondents can switch from being anonymous to not anonymous by providing data
        valid_payload_to_full = {
            'is_anonymous':False,
            'id_no': '12345',
            'first_name': 'Test',
            'last_name': 'Testerson',
            'dob': '2000-01-01',
            'ward': 'Here',
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/', valid_payload_to_full, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_anon.refresh_from_db()
        self.assertEqual(self.respondent_anon.ward, 'Here')

        #test that a respondent can opt into being anonymous and have PII deleted
        valid_payload_to_anon = {
            'is_anonymous':True,
            'age_range': Respondent.AgeRanges.ET_24,
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_payload_to_anon, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        self.assertEqual(self.respondent_full.id_no, None)

    
    
    def test_delete_respondent(self):
        #only admins can delete
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/record/respondents/{self.respondent_full.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_delete_respondent_no_perm(self):
        #your not allowed
        self.client.force_authenticate(user=self.officer)
        response = self.client.delete(f'/api/record/respondents/{self.respondent_full.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_respondent_inter(self):
        #interactions should block respondent from being deleted
        self.client.force_authenticate(user=self.admin)
        client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        project = Project.objects.create(
            name='Gamma Project',
            client= client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        indicator = Indicator.objects.create(code='1', name='Test Ind')
        project.organizations.set([self.org])
        project.indicators.set([indicator])
        task = Task.objects.create(project=project, organization=self.org, indicator=indicator)

        interaction = Interaction.objects.create(respondent=self.respondent_full, interaction_date='2025-06-23', task=task)
        response = self.client.delete(f'/api/record/respondents/{self.respondent_full.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_create_respondent_client(self):
        #test creating both anonymous and full respondent_anonprofiles
        self.client.force_authenticate(user=self.client_user)
        valid_payload_anon = {
            'is_anonymous':True,
            'age_range': Respondent.AgeRanges.ET_24,
            'village': 'Here', 
            'citizenship': 'Test',
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
        }

        response = self.client.post('/api/record/respondents/', valid_payload_anon, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_respondent_client(self):
        #test basic patch operation
        valid_patch = {
            'ward': 'There'
        }
        self.client.force_authenticate(user=self.client_user)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class SensitiveInfoViewSetTest(APITestCase):
    def setUp(self):
        #set up users, organizations, and respondents
        self.today = date.today().isoformat()
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.officer = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
        self.org = Organization.objects.create(name='Test Org')
        
        self.admin.organization = self.org
        self.officer.organization = self.org
        self.data_collector.organization = self.org
        self.client_user.organization = self.org

        self.respondent_anon= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.ET_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

    def test_sensitive_info_create(self):
        #test a patch akin to how to website sends this information
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
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/sensitive-info/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_anon.refresh_from_db()
        self.assertEqual(self.respondent_anon.disability_status.count(), 2)
        self.assertEqual(self.respondent_anon.kp_status.count(), 2)
    
    def test_sensitive_info_patch(self):
        #edit patch
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'kp_status_names': ['MSM'],
            'disability_status_names': ['VI', 'PD', 'SI'],
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/sensitive-info/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_anon.refresh_from_db()
        self.assertEqual(self.respondent_anon.disability_status.count(), 3)
        self.assertEqual(self.respondent_anon.kp_status.count(), 1)
    
    def test_sensitive_info_sans_dates(self):
        #test if just bools are provided the dates are automatically filled in
        #at least for now, this is how the app sends the data
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'is_pregnant': True,
            'hiv_positive': True,
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/sensitive-info/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_anon.refresh_from_db()
        pregnancy = Pregnancy.objects.filter(respondent=self.respondent_anon).first()
        hiv_status = HIVStatus.objects.filter(respondent=self.respondent_anon).first()
        self.assertEqual(pregnancy.term_began, date.today())
        self.assertEqual(hiv_status.hiv_positive, True)
        self.assertEqual(hiv_status.date_positive, date.today())
    
    def test_sensitive_info_date_only(self):
        #make sure that term ended ends the pregnancy
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'is_pregnant': True,
            'term_ended': '2025-6-20',
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/sensitive-info/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_anon.refresh_from_db()
        pregnancy = Pregnancy.objects.filter(respondent=self.respondent_anon).first()
        self.assertEqual(pregnancy.is_pregnant, False)
        self.assertEqual(pregnancy.term_ended, date(2025, 6, 30))
    
    def test_sensitive_info_date_only(self):
        #make sure sending false ends the pregnancy automatically
        self.client.force_authenticate(user=self.data_collector)
        pregnancy = Pregnancy.objects.create(respondent=self.respondent_anon, is_pregnant=True, term_began=date(2024, 6, 30))
        valid_payload = {
            'is_pregnant': False,
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/sensitive-info/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pregnancy.refresh_from_db()
        self.assertEqual(pregnancy.is_pregnant, False)
        self.assertEqual(pregnancy.term_ended, date.today())

    def test_sensitive_info_client_patch(self):
        #edit patch
        self.client.force_authenticate(user=self.client_user)
        valid_payload = {
            'kp_status_names': ['MSM'],
            'disability_status_names': ['VI', 'PD', 'SI'],
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/sensitive-info/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class RespondentBulkUploadTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin', password='pass', role='admin')
        self.client.force_authenticate(self.user)
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
        self.org = Organization.objects.create(name="Org")
        self.client_user.organization = self.org
        self.user.organization = self.org

        self.project = Project.objects.create(name="Delta Project", start='2024-01-01', end='2025-12-31')
        self.project.organizations.set([self.org])

        self.indicator = Indicator.objects.create(code='TEST', name='Test Indicator')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        self.indicator.subcategories.set([category, category2])
        self.indicator_num = Indicator.objects.create(code='TEST', name='Test Indicator', require_numeric=True)
        self.project.indicators.set([self.indicator, self.indicator_num])
        self.task = Task.objects.create(indicator=self.indicator, organization=self.org, project=self.project)
        self.task_num = Task.objects.create(indicator= self.indicator_num, organization=self.org, project=self.project)
        self.url = reverse('respondent-bulk-upload')  # or '/api/record/respondents/bulk/' if not using routers

    def test_bulk_upload_valid_data(self):
        payload = [
            {
                "id_no": "123456",
                "first_name": "Test",
                "last_name": "User",
                "dob": "2000-01-01",
                "sex": "M",
                "village": 'here',
                "district": "Central",
                "citizenship": "Motswana",
                "is_anonymous": False,
                "sensitive_info": {
                    "hiv_positive": True,
                    "date_positive": "2020-01-01"
                },
                "interactions": [
                    {
                        "interaction_date": '2025-05-01',
                        "task": self.task.id,
                        "subcategory_names": ["foo", "bar"]
                    },
                    {
                        "interaction_date": '2025-05-02',
                        "task": self.task_num.id,
                        "numeric_component": 12
                    }
                ]
            }
        ]

        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_bulk_upload_invalid_data(self):
        payload = [{"id_no": "", "first_name": "Missing Last Name"}]

        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_207_MULTI_STATUS)
        self.assertEqual(len(response.data['errors']), 1)
    
    def test_bulk_client(self):
        #edit patch
        self.client.force_authenticate(user=self.client_user)
        payload = [
            {
                "id_no": "123456",
                "first_name": "Test",
                "last_name": "User",
                "dob": "2000-01-01",
                "sex": "M",
                "village": 'here',
                "district": "Central",
                "citizenship": "Motswana",
                "is_anonymous": False,
                "sensitive_info": {
                    "hiv_positive": True,
                    "date_positive": "2020-01-01"
                },
                "interactions": [
                    {
                        "interaction_date": '2025-05-01',
                        "task": self.task.id,
                        "subcategory_names": ["foo", "bar"]
                    },
                    {
                        "interaction_date": '2025-05-02',
                        "task": self.task_num.id,
                        "numeric_component": 12
                    }
                ]
            }
        ]
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)