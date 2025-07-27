from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from organizations.models import Organization
from projects.models import Project, Client
from indicators.models import Indicator, IndicatorSubcategory

User = get_user_model()


class TestIndicatorValidation(APITestCase):
    def setUp(self):
        self.parent = Organization.objects.create(name='Parent Org')
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.parent)
        self.officer = User.objects.create_user(username='officer', password='testpass', role='meofficer', organization=self.parent)
        self.indicator = Indicator.objects.create(name='Test Indicator', code='TEST101')
        self.prereq_resp = Indicator.objects.create(name='Prereq', code='PRE', indicator_type='respondent')
        self.prereq_planned = Indicator.objects.create(name='Planned', code='PL', status='planned')
        self.dep =Indicator.objects.create(name='Dep', code='DEP')
        self.dep.prerequisites.set([self.prereq_resp])
    
    def test_queryset_admin(self):
        '''
        Admins can see all indicators
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/indicators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 4)
    
    def test_queryset_meofficer(self):
        '''
        ME officers can only see active indicators.
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.get('/api/indicators/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_create_admin(self):
        '''
        Indicators can be created with the below payload.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
            'status': 'active',
            'indicator_type': 'respondent',
        }
        response = self.client.post('/api/indicators/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_meofficer(self):
        '''
        Other roles cannot create indicators.
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
            'status': 'active',
            'indicator_type': 'respondent',
        }
        response = self.client.post('/api/indicators/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_meofficer(self):
        '''
        Or update them. 
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'name': 'Ind 3',
            'code': '3',
            'status': 'active',
            'indicator_type': 'respondent',
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_delete_admin(self):
        '''
        Admins cannot delete indicators with a prereq.
        '''
        #but not if they have a prerequisite
        response = self.client.delete(f'/api/indicators/{self.indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_delete_meofficer(self):
        '''
        But no one slse
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.delete(f'/api/indicators/{self.indicator.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_prereq(self):
        '''
        Test that indicators can also be created with prereqs
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': 'NEW101',
            'indicator_type': 'respondent',
            'prerequisite_ids': [self.indicator.id, self.dep.id]
        }
        response = self.client.post(f'/api/indicators/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        indicator = Indicator.objects.get(code='NEW101')
        self.assertEqual(indicator.prerequisites.count(), 2)

    def test_no_code(self):
        '''
        Code is required
        '''
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'name': 'Ind 3',
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_no_name(self):
        '''
        So is name.
        '''
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'code': '3'
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicates(self):
        '''
        Duplicate names/codes should throw an error.
        '''
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

    def test_invalid_prereq(self):
        '''
        Mismatched prereq types (i.e., respondent versus count) should fail, since thats impossible. 
        '''
        self.client.force_authenticate(user=self.admin)
        #wrong type should fail
        invalid_payload = {
            'name': 'Ind 3',
            'code': 'PRE102',
            'indicator_type': 'count',
            'prerequisite_ids': [self.prereq_resp.id],
            'status': 'active',
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        '''
        Mixed statuses is also weird, and should be flagged. 
        '''
        invalid_payload = {
            'name': 'Ind 3',
            'code': 'PRE102',
            'status': 'active',
            'indicator_type': 'respondent',
            'prerequisite_ids': [self.prereq_planned.id]
        }
        response = self.client.post(f'/api/indicators/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_dependency(self):
        '''
        Test patching statuses doesn't invalidate downstream indicators.
        '''
        self.client.force_authenticate(user=self.admin)
        #wrong type should fail
        invalid_payload = {
            'status': 'planned'
        }
        response = self.client.patch(f'/api/indicators/{self.prereq_resp.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'indicator_type': 'count'
        }
        response = self.client.patch(f'/api/indicators/{self.prereq_resp.id}/', invalid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_self_prereq(self):
        '''
        Make sure an indicator can't be its own prereq, since that could create an infinite loop.
        '''
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'prerequisite_ids': [self.indicator.id]
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
        '''
        Test subcats can be created (no ids passed)
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': 'NEW101',
            'status': 'active',
            'indicator_type': 'respondent',
            'subcategory_data': [{'id': None, 'name': 'New 1'}, {'id': None, 'name': 'New 2'}],
        }
        response = self.client.post(f'/api/indicators/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ind = Indicator.objects.filter(code='NEW101').first()

        self.assertEqual(ind.subcategories.count(), 2)
        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 4)
    
    def test_update_name(self):
        '''
        Test subcat names can be updated
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'subcategory_data': [{'id': self.cat1.id , 'name': 'Category 1'}, {'id': self.cat2.id, 'name': 'Category 2'}],
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.indicator.subcategories.count(), 2)
        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 2)
    
    def test_depr(self):
        '''
        Test they can be deprecated
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'subcategory_data': [{'id': self.cat1.id , 'name': 'Category 1', 'deprecated': False}, {'id': self.cat2.id, 'name': 'Category 2', 'deprecated': True}],
        }
        response = self.client.patch(f'/api/indicators/{self.indicator.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        all_cats = IndicatorSubcategory.objects.filter(deprecated=False)
        self.assertEqual(all_cats.count(), 1)
    
    def test_create_match(self):
        '''
        Test subcategories can be matched to a prereq.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Ind 3',
            'code': 'NEW101',
            'status': 'active',
            'indicator_type': 'respondent',
            'prerequisite_ids': [self.indicator.id, self.dependent.id],
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
        '''
        Test that updates to an indicators subcats will affect downstream indicators as well.
        '''
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
        '''
        Test that subcats can be unmatched and reset.
        '''
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
        '''
        Test that subcats can be unmatched a cleared.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'match_subcategories_to': None,
        }
        response = self.client.patch(f'/api/indicators/{self.dependent.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.dependent.subcategories.count(), 0)
        