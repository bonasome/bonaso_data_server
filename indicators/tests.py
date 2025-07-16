from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from organizations.models import Organization
from projects.models import Project, Client
from indicators.models import Indicator, IndicatorSubcategory

User = get_user_model()


class TestIndicatorPerms(APITestCase):
    def setUp(self):
        self.client_obj = Client.objects.create(name='Test Client')  # Assuming Client exists

        self.parent = Organization.objects.create(name='Parent Org')
        self.child = Organization.objects.create(name='Child Org', parent_organization=self.parent)
        self.wrong = Organization.objects.create(name='Wrong Org')

        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.parent)
        self.meofficer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer', organization=self.parent)
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager', organization=self.parent)
        self.mechild = User.objects.create_user(username='mechild', password='testpass', role='meofficer', organization=self.child)
        self.wrong_org = User.objects.create_user(username='wrong_org', password='testpass', role='meofficer', organization=self.wrong)
        self.data_collector = User.objects.create_user(username='dc', password='testpass', role='data_collector', organization=self.parent)
        self.view_only = User.objects.create_user(username='view', password='testpass', role='view_only', organization=self.parent)
        self.no_org = User.objects.create_user(username='orgless', password='testpass', role='meofficer')
        self.no_role = User.objects.create_user(username='norole', password='testpass')  # no role

        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent, self.wrong])

        self.indicator = Indicator.objects.create(code='Test101', name='Test')
        self.inactive_ind = Indicator.objects.create(code='Test102', name='Inactive', status=Indicator.Status.PLANNED)
        self.wrong_prog = Indicator.objects.create(code='Test103', name='Not in proj')
        self.project.indicators.set([self.indicator])


    def test_queryset_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/indicators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_queryset_meofficer(self):
        self.client.force_authenticate(user=self.meofficer)
        response = self.client.get('/api/indicators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_create_admin(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
        }
        response = self.client.post('/api/indicators/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_meofficer(self):
        self.client.force_authenticate(user=self.meofficer)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
        }
        response = self.client.post('/api/indicators/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_meofficer(self):
        self.client.force_authenticate(user=self.meofficer)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/indicators/{self.inactive_ind.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        response = self.client.delete(f'/api/indicators/{self.indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_meofficer(self):
        self.client.force_authenticate(user=self.meofficer)
        response = self.client.delete(f'/api/indicators/{self.indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class TestIndicatorValidation(APITestCase):
    def setUp(self):
        self.parent = Organization.objects.create(name='Parent Org')
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.parent)
        self.indicator = Indicator.objects.create(name='Test Indicator', code='TEST101')
        self.prereq_resp = Indicator.objects.create(name='Prereq', code='PRE')
        self.prereq_planned = Indicator.objects.create(name='Planned', code='PL', status='Planned')
        self.dep =Indicator.objects.create(name='Dep', code='DEP')
        self.dep.prerequisites.set([self.prereq_resp])
    
    def test_create(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': 'NEW101',
            'subcategory_data': [{'id': None,'name': 'Cat 1'}, {'id': None,'name': 'Cat 2'}],
        }
        response = self.client.post(f'/api/indicators/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        indicator = Indicator.objects.get(code='NEW101')
        self.assertEqual(indicator.subcategories.count(), 2)
        subcategory_names = list(indicator.subcategories.values_list('name', flat=True))
        self.assertListEqual(sorted(subcategory_names), ['Cat 1', 'Cat 2'])

    def test_create_prereq(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': 'NEW101',
            'indicator_type': 'Respondent',
            'prerequisite_id': [self.indicator.id, self.dep.id]
        }
        response = self.client.post(f'/api/indicators/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        indicator = Indicator.objects.get(code='NEW101')
        self.assertEqual(indicator.prerequisites.count(), 2)

    def test_patch(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'subcategory_data': [{'id': None, 'name': 'Cat 1'}],
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.indicator.subcategories.count(), 1)
        subcategory_names = list(self.indicator.subcategories.values_list('name', flat=True))
        self.assertListEqual(sorted(subcategory_names), ['Cat 1'])

    def test_no_code(self):
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'name': 'Ind 3',
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_name(self):
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'code': '3'
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicates(self):
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'name': 'Ind 3',
            'code': 'TEST101',
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'name': 'Test Indicator',
            'code': 'TEST102',
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_prereq(self):
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'name': 'Ind 3',
            'code': 'PRE102',
            'indicator_type': 'Respondent',
            'status': 'Planned',
            'prerequisite_id': [self.prereq_planned.id]
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_invalid_prereq(self):
        self.client.force_authenticate(user=self.admin)
        #wrong type should fail
        invalid_payload = {
            'name': 'Ind 3',
            'code': 'PRE102',
            'indicator_type': 'Count',
            'prerequisite_id': [self.prereq_resp.id]
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #as should bad mixed statuses
        invalid_payload = {
            'name': 'Ind 3',
            'code': 'PRE102',
            'status': 'Active',
            'indicator_type': 'Respondent',
            'prerequisite_id': [self.prereq_planned.id]
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_dependency(self):
        self.client.force_authenticate(user=self.admin)
        #wrong type should fail
        invalid_payload = {
            'status': 'Planned'
        }
        response = self.client.patch(f'/api/indicators/{self.prereq_resp.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'indicator_type': 'Count'
        }
        response = self.client.patch(f'/api/indicators/{self.prereq_resp.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_self_prereq(self):
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'prerequisite_id': [self.indicator.id]
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

class TestIndicatorSubcategories(APITestCase):
    def setUp(self):

        self.org = Organization.objects.create(name='Parent Org')
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.org)

        self.cat1 = IndicatorSubcategory.objects.create(name='Cat 1', slug='cat1')
        self.cat2 = IndicatorSubcategory.objects.create(name='Cat 2', slug='cat2')
        self.dep = IndicatorSubcategory.objects.create(name='Dep', slug='dep', deprecated=True)
        self.indicator = Indicator.objects.create(code='Test101', name='Test')
        self.indicator.subcategories.set([self.cat1, self.cat2])
        self.dependent = Indicator.objects.create(code='Dep101', name='Dep', match_subcategories_to=self.indicator)
        self.dependent.prerequisites.set([self.indicator])
        self.dependent.subcategories.set([self.cat1, self.cat2])

    def test_create_subcats(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': 'NEW101',
            'subcategory_names': [{'id': None, 'name': 'New 1'}, {'id': None, 'name': 'New 2'}],
        }
        response = self.client.post(f'/api/indicators/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ind = Indicator.objects.filter(code='NEW101').first()

        self.assertEqual(ind.subcategories.count(), 2)
        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 4)
    
    def test_update_name(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'subcategory_names': [{'id': self.cat1.id , 'name': 'Category 1'}, {'id': self.cat2.id, 'name': 'Category 2'}],
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.indicator.subcategories.count(), 2)
        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 2)
    
    def test_depr(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'subcategory_names': [{'id': self.cat1.id , 'name': 'Category 1', 'deprecated': False}, {'id': self.cat2.id, 'name': 'Category 2', 'deprecated': True}],
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 1)
    
    def test_create_match(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': 'NEW101',
            'prerequisite_id': [self.indicator.id, self.dependent.id],
            'indicator_type': 'Respondent',
            'match_subcategories_to': self.indicator.id,
        }
        response = self.client.post(f'/api/indicators/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ind = Indicator.objects.filter(code='NEW101').first()
        self.assertEqual(ind.subcategories.count(), 2)
        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 2)
        cat_ids = [c.id for c in ind.subcategories.all()]
        self.assertEqual(cat_ids, [self.cat1.id, self.cat2.id])
    
    def test_patch_update_cascade(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'subcategory_data': [{'id': self.cat1.id, 'name': 'Cat 1'}, {'id': self.cat2.id, 'name': 'Cat 2'},
                {'id': None, 'name': 'Cat 3'}]
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.dependent.subcategories.count(), 3)

    def test_patch_unmatch(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'match_subcategories_to': None,
            'subcategory_data': [{'id': None, 'name': 'Screw You Indicator 1'}]
        }
        response = self.client.patch(f'/api/indicators/{self.dependent.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.dependent.subcategories.count(), 1)
        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 3)

    def test_patch_unmatch_clear(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'match_subcategories_to': None,
        }
        response = self.client.patch(f'/api/indicators/{self.dependent.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.dependent.subcategories.count(), 0)
        