from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from projects.models import Project, Client, Task
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, RespondentAttributeType
from organizations.models import Organization
from indicators.models import Indicator, IndicatorSubcategory
from datetime import date
from respondents.utils import calculate_age_range, dummy_dob_calc
User = get_user_model()

class RespondentViewSetTest(APITestCase):
    '''
    This one is mostly for the respondent serializer, but has some overlap with the viewset for gets.
    '''

    def setUp(self):
        self.today = date.today().isoformat()
        
        #setup our users
        self.admin = User.objects.create_user(username='testuser', password='testpass', role='admin')
        self.officer = User.objects.create_user(username='testuser2', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
        
        #create an org (no real org perms for respondents so no need to create another)
        self.org = Organization.objects.create(name='Test Org')
        
        self.admin.organization = self.org
        self.officer.organization = self.org
        self.data_collector.organization = self.org
        self.client_user.organization = self.org

        #existing anon respondent
        self.respondent_anon= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

        #existing full respondent
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
        '''
        Make sure respondents list returns all respondents, no special org/role permissions. 
        All respondents should be public.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/record/respondents/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_create_respondent(self):
        '''
        Make sure that creation works for both full and anonymous respondents. This includes making sure that 
        pregnancy/hiv status and the m2m fields successfully update. Also, confirm that our age range 
        system and auto DOB calculation for anonymous respondents works.
        '''
        self.client.force_authenticate(user=self.data_collector)

        #sample anon payload
        valid_payload_anon = {
            'is_anonymous':True,
            'age_range': Respondent.AgeRanges.T_24,
            'village': 'Here', 
            'citizenship': 'Test',
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
            'kp_status_names': ['MSM'],
            'disability_status_names': ['VI', 'PD', 'SI'],
            'hiv_status_data': {'hiv_positive': True, 'date_positive': '2024-01-01'},
            'pregnancy_data': [{'term_began': '2021-01-01', 'term_ended': '2021-09-01'}, {'term_began': '2024-01-01'}]
        }

        response = self.client.post('/api/record/respondents/', valid_payload_anon, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent_anon= Respondent.objects.get(village='Here')
        self.assertEqual(respondent_anon.village,'Here')
        self.assertEqual(respondent_anon.created_by, self.data_collector)
        self.assertEqual(respondent_anon.kp_status.count(), 1)
        self.assertEqual(respondent_anon.disability_status.count(), 3)
        self.assertEqual(HIVStatus.objects.filter(respondent=respondent_anon).count(), 1)
        self.assertEqual(HIVStatus.objects.filter(respondent=respondent_anon).first().date_positive, date(2024,1,1))
        self.assertEqual(Pregnancy.objects.filter(respondent=respondent_anon).count(), 2)
        dummy_dob = dummy_dob_calc(respondent_anon.age_range, respondent_anon.created_at) #should be the same since no DOB was provided
        self.assertEqual(respondent_anon.effective_dob, dummy_dob)

        #sample full payload
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
            'special_attribute_names': ['CHW', 'Staff']
        }

        response = self.client.post('/api/record/respondents/', valid_payload_full, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent= Respondent.objects.get(village='Place')
        self.assertEqual(respondent.id_no,'1234')
        self.assertEqual(respondent.special_attribute.count(), 2)
        ar = calculate_age_range(respondent.dob) 
        self.assertEqual(respondent.age_range, ar) #should be automatically set since DOB was provided

    def test_create_duplicate(self):
        '''
        If you were paying attention in the serializer section, you would know that we do not allow duplicates.
        Make sure this returns a 409.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload_full = {
            'is_anonymous': False,
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
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn('existing_id', response.data) #make sure the existing id is returned since the frontend will use this to redirect
        self.assertEqual(int(response.data['existing_id']), self.respondent_full.id) #also for good measure assert its the right ID

    def test_patch_respondent(self):
        '''
        Test a few patch operations to cover our bases. While we will mostly be dealing with complete requests
        from the front end, we want to handle partial patches gracefully.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_patch = {
            'kp_status_names': ['MSM', 'TG']
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        self.assertEqual(self.respondent_full.kp_status.count(), 2)
        self.assertEqual(self.respondent_full.updated_by, self.data_collector)

        valid_patch_2 = {
            'disability_status_names': ['VI']
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch_2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        self.assertEqual(self.respondent_full.kp_status.count(), 2)
        self.assertEqual(self.respondent_full.disability_status.count(), 1)
        
        valid_patch_3 = {
            'disability_status_names': []
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch_3, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        self.assertEqual(self.respondent_full.kp_status.count(), 2)
        self.assertEqual(self.respondent_full.disability_status.count(), 0)

    def test_switch_respondent_type(self):
        '''
        Test to confirm that switching respondent types works. Especially that the dummy dob/age range
        calculations adjust.
        '''
        valid_payload_to_full = {
            'is_anonymous':False,
            'id_no': '12345',
            'first_name': 'Test',
            'last_name': 'Testerson',
            'dob': '1975-01-01',
            'ward': 'Here',
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_anon.id}/', valid_payload_to_full, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_anon.refresh_from_db()
        self.assertEqual(self.respondent_anon.ward, 'Here')
        self.assertEqual(self.respondent_anon.effective_dob, date(1975, 1, 1)) #make sure we're now using the DOB
        ar = calculate_age_range(self.respondent_anon.dob)
        self.assertEqual(self.respondent_anon.age_range, ar)

        #test that a respondent can opt into being anonymous and have PII deleted
        valid_payload_to_anon = {
            'is_anonymous':True,
            'age_range': '40_44',
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_payload_to_anon, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        self.assertEqual(self.respondent_full.id_no, None)
        self.assertEqual(self.respondent_full.age_range, '40_44')
        dummy_dob = dummy_dob_calc(self.respondent_full.age_range, self.respondent_full.created_at)
        self.assertEqual(self.respondent_full.effective_dob, dummy_dob)

    def test_manage_preg(self):
        '''
        Specifically check that patching/creating/removing respondent pregnancies works. 
        '''

        #check that effective creation works
        valid_patch = {
            'pregnancy_data': [
                {'id': None, 'term_began': '2024-01-01', 'term_ended': None},
                {'id': None, 'term_began': '2022-01-01', 'term_ended': '2022-09-01'}
            ]
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        pregnancies = Pregnancy.objects.filter(respondent=self.respondent_full).count()
        self.assertEqual(pregnancies, 2)
        target_p = Pregnancy.objects.filter(respondent=self.respondent_full, term_began=date(2024, 1, 1)).first()
        self.assertEqual(target_p.created_by, self.data_collector)
        
        #also check that partial updates work as intended
        valid_patch_2 = {
            'pregnancy_data': [
                {'id': target_p.id, 'term_began': '2024-01-01', 'term_ended': '2024-09-01'},
            ]
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch_2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        pregnancies = Pregnancy.objects.filter(respondent=self.respondent_full).count()
        target_p.refresh_from_db()
        self.assertEqual(pregnancies, 2)
        self.assertEqual(target_p.updated_by, self.data_collector)

        #effective delete
        valid_patch_3 = {
            'pregnancy_data': [
                {'id': target_p.id, 'term_began': None, 'term_ended': None},
            ]
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch_3, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        pregnancies = Pregnancy.objects.filter(respondent=self.respondent_full).count()
        self.assertEqual(pregnancies, 1)
    
    def test_manage_hiv(self):
        '''
        Test that a user can patch/manage HIV statuses (positive/date)
        '''
        valid_patch = {
            'hiv_status_data': {'hiv_positive': True, 'date_positive': '2024-04-01'}
        }
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        hiv = HIVStatus.objects.filter(respondent=self.respondent_full, hiv_positive=True).count()
        self.assertEqual(hiv, 1)
        hiv1 = HIVStatus.objects.filter(respondent=self.respondent_full, hiv_positive=True).first()
        self.assertEqual(hiv1.created_by, self.data_collector)

        valid_patch2 = {
            'hiv_status_data': {'hiv_positive': False}
        }
        response = self.client.patch(f'/api/record/respondents/{self.respondent_full.id}/', valid_patch2, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.respondent_full.refresh_from_db()
        hiv = HIVStatus.objects.filter(respondent=self.respondent_full, hiv_positive=True).count()
        self.assertEqual(hiv, 0)
        hiv1 = HIVStatus.objects.filter(respondent=self.respondent_full, hiv_positive=False).first()
        hiv1.refresh_from_db()
        self.assertEqual(hiv1.updated_by, self.data_collector)

    def test_bad_omang(self):
        '''
        Test that our flagging system automatically flags sus Omangs. Also check that it automatically
        resolves them if the id is corrected.
        '''
        self.client.force_authenticate(user=self.data_collector)
        flag_payload = {
            'is_anonymous':False,
            'id_no': '000000', #wrong number of digits
            'first_name': 'Test',
            'last_name': 'Testerson',
            'dob': '2000-01-01',
            'ward': 'Here',
            'village': 'Place', 
            'citizenship': 'BW', #this should only work for citizens
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
        }

        response = self.client.post('/api/record/respondents/', flag_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent = Respondent.objects.filter(id_no = '000000').first()
        self.assertEqual(respondent.flags.count(), 3)

        valid_patch = {
            'id_no': '111121111' #corrected # of digits and fifth digit
        }
        response = self.client.patch(f'/api/record/respondents/{respondent.id}/', valid_patch, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(respondent.flags.filter(resolved=True).count(), 3)

    def test_not_fire_non_citizen(self):
        '''
        Omang rules do not apply to non-citizens, so no auto-flags should be generated.
        '''
        self.client.force_authenticate(user=self.data_collector)
        flag_payload = {
            'is_anonymous':False,
            'id_no': '000000', #wrong number of digits
            'first_name': 'Test',
            'last_name': 'Testerson',
            'dob': '2000-01-01',
            'ward': 'Here',
            'village': 'Place', 
            'citizenship': 'American', #this should only work for citizens
            'sex': Respondent.Sex.FEMALE,
            'district': Respondent.District.CENTRAL,
        }

        response = self.client.post('/api/record/respondents/', flag_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        respondent = Respondent.objects.filter(id_no = '000000').first()
        self.assertEqual(respondent.flags.count(), 0)

    def test_delete_respondent(self):
        '''
        Make sure admins can delete. This is not encouraged behavior, but the capacity should be there for 
        whatever may come.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/record/respondents/{self.respondent_full.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
    
    def test_delete_respondent_no_perm(self):
        '''
        No one else though
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.delete(f'/api/record/respondents/{self.respondent_full.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_respondent_inter(self):
        '''
        If a respondent has any interactions, they should not be deleteable.
        '''
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
        task = Task.objects.create(project=project, organization=self.org, indicator=indicator)

        interaction = Interaction.objects.create(respondent=self.respondent_full, interaction_date='2025-06-23', task=task)
        response = self.client.delete(f'/api/record/respondents/{self.respondent_full.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        

    def test_create_respondent_client(self):
        #test creating both anonymous and full respondent_anonprofiles
        self.client.force_authenticate(user=self.client_user)
        valid_payload_anon = {
            'is_anonymous':True,
            'age_range': Respondent.AgeRanges.T_24,
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
        self.category = IndicatorSubcategory.objects.create(name='Cat 1')
        self.category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        self.indicator.subcategories.set([self.category, self.category2])
        self.indicator_num = Indicator.objects.create(code='TEST', name='Test Indicator', require_numeric=True)

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
                "citizenship": "BW",
                "is_anonymous": False,
                "sensitive_info": {
                    "hiv_positive": True,
                    "date_positive": "2020-01-01"
                },
                "interactions": [
                    {
                        "interaction_date": '2025-05-01',
                        "task": self.task.id,
                        "subcategories_data": [{'id': None, 'subcategory': {'name':'Cat 1', 'id': self.category.id}}, {'id': None, 'subcategory': {'name': 'Cat 2', 'id': self.category2.id}}]
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
                "citizenship": "BW",
                "is_anonymous": False,
                "sensitive_info": {
                    "hiv_positive": True,
                    "date_positive": "2020-01-01"
                },
                "interactions": [
                    {
                        "interaction_date": '2025-05-01',
                        "task": self.task.id,
                        "subcategory_names": [{'name':'Cat 1', 'id': self.category.id}, {'name': 'Cat 2', 'id': self.category2.id}]
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