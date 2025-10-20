from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from organizations.models import Organization
from projects.models import Project, Client, Task
from indicators.models import Indicator, Assessment, Option, LogicGroup, LogicCondition

User = get_user_model()

class TestIndicators(APITestCase):
    '''
    Test indicator creation/validation logic.
    '''
    def setUp(self):
        self.parent = Organization.objects.create(name='Parent Org')
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin', organization=self.parent)
        self.officer = User.objects.create_user(username='officer', password='testpass', role='meofficer', organization=self.parent)

        self.assessment = Assessment.objects.create(name='Ass')
        self.indicator = Indicator.objects.create(name='Ind 1', type=Indicator.Type.MULTI, assessment=self.assessment, order=0)
        self.option = Option.objects.create(name='Option 1', indicator=self.indicator)
        self.indicator_txt = Indicator.objects.create(name='Ind Txt', type=Indicator.Type.TEXT, assessment=self.assessment , order=1)
        self.indicator_int = Indicator.objects.create(name='Ind Int', type=Indicator.Type.INT, assessment=self.assessment, order=2)
        self.indicator_single = Indicator.objects.create(name='Ind Single', type=Indicator.Type.SINGLE, assessment=self.assessment, order=3)
        self.option_single = Option.objects.create(name='Single Option', indicator=self.indicator_single)
    
    def test_create_ass(self):
        '''
        Assessments can be created with the below payload.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Test Assessment',
        }
        response = self.client.post('/api/indicators/assessments/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_edit_ass(self):
        '''
        Assessments can be created with the below payload.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Assessment',
        }
        response = self.client.patch(f'/api/indicators/assessments/{self.assessment.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.name, 'Assessment')
        self.assertEqual(self.assessment.updated_by, self.admin)

    def test_create_indicators_ass(self):
        '''
        Test out a couple types of indicators for an assessment.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Screened for NCDs',
            'type': Indicator.Type.MULTI,
            'category': Indicator.Category.ASS,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'options_data': [{'name': 'BMI'}, {'name': 'Blood Pressure'}, {'name': 'Blood Glucose'},],
            'allow_none': True,
            'logic_data': {}
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        ind = Indicator.objects.filter(name='Screened for NCDs').first()
        options = Option.objects.filter(indicator=ind)
        self.assertEqual(options.count(), 3)
        self.assertEqual(LogicCondition.objects.filter(group__indicator=ind).count(), 0)
        self.assertEqual(ind.created_by, self.admin)

        valid_payload = {
            'name': 'Referred for NCDs',
            'type': Indicator.Type.MULTI,
            'category': Indicator.Category.ASS,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'match_options_id': ind.id,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': ind.id,
                        'operator': '=',
                        'condition_type': 'any'
                    }
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ind2 = Indicator.objects.filter(name='Referred for NCDs').first()
        logic = LogicCondition.objects.filter(group__indicator=ind2)
        self.assertEqual(logic.count(), 1)
        self.assertEqual(logic.first().source_indicator, ind)
        self.assertEqual(logic.first().condition_type, 'any')

        valid_payload = {
            'name': 'Something else for NCDs',
            'type': Indicator.Type.TEXT,
            'category': Indicator.Category.ASS,
            'assessment_id': self.assessment.id,
            'allow_aggregate': False,
            'required': False,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': ind2.id,
                        'operator': '!=',
                        'value_option': Option.objects.filter(name='BMI').first().id
                    },
                    {
                        'source_type': LogicCondition.SourceType.RES,
                        'respondent_field': LogicCondition.RespondentField.SEX,
                        'operator': '=',
                        'value_text': 'M'
                    }
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ind3 = Indicator.objects.filter(name='Something else for NCDs').first()
        logic = LogicCondition.objects.filter(group__indicator=ind3)
        self.assertEqual(logic.count(), 2)
    
    def test_edit_indicator_ass(self):
        '''
        Assessments can be created with the below payload.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'New and Improved',
            'options_data': [{'name': 'New Option 1' }, {'name': 'New Option 2' }]
        }
        response = self.client.patch(f'/api/indicators/manage/{self.indicator.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.indicator.refresh_from_db()
        self.option.refresh_from_db()
        self.assertEqual(self.indicator.updated_by, self.admin)
        self.assertEqual(self.indicator.name, 'New and Improved')
        self.assertEqual(Option.objects.filter(indicator=self.indicator, deprecated=False).count(), 2)
        self.assertEqual(self.option.deprecated, True)

    def test_bad_logic(self):
        '''
        Test a sampling of bad logic. There's like a million permutations of bad logic
        but try to hit at least most of that code.
        '''
        self.client.force_authenticate(user=self.admin)
        # invalid source indicator
        invalid_payload = {
            'name': 'Something else for NCDs',
            'type': Indicator.Type.TEXT,
            'category': Indicator.Category.ASS,
            'assessment_id': self.assessment.id,
            'allow_aggregate': False,
            'required': False,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': 100043,
                        'operator': '=',
                        'value_option': self.option.id
                    },
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # invalid option_id
        invalid_payload = {
            'name': 'Something else for NCDs',
            'type': Indicator.Type.TEXT,
            'category': Indicator.Category.ASS,
            'assessment_id': self.assessment.id,
            'allow_aggregate': False,
            'required': False,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': self.indicator.id,
                        'operator': '=',
                        'value_option': self.option_single.id,
                    },
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # option for wrong indicator type
        invalid_payload = {
            'name': 'Something else for NCDs',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.TEXT,
            'assessment_id': self.assessment.id,
            'allow_aggregate': False,
            'required': False,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': self.indicator_txt.id,
                        'operator': '=',
                        'value_option': self.option.id 
                    },
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # bad conditional type
        invalid_payload = {
            'name': 'Something else for NCDs',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.TEXT,
            'assessment_id': self.assessment.id,
            'allow_aggregate': False,
            'required': False,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': self.indicator_single.id,
                        'operator': '=',
                        'condition_type': 'all'
                    },
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # bad operator 
        invalid_payload = {
            'name': 'Something else for NCDs',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.TEXT,
            'assessment_id': self.assessment.id,
            'allow_aggregate': False,
            'required': False,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': self.indicator_single.id,
                        'operator': 'DNC',
                        'value_option': self.option_single.id
                    },
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # bad operator II
        invalid_payload = {
            'name': 'Something else for NCDs',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.TEXT,
            'assessment_id': self.assessment.id,
            'allow_aggregate': False,
            'required': False,
            'logic_data': {'group_operator': 'AND', 
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': self.indicator_txt.id,
                        'operator': '<',
                        'value_text': 7
                    },
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # not an assessment indicator
        invalid_payload = {
            'name': 'Something else for NCDs',
            'category': Indicator.Category.MISC,
            'logic_data': {
                'group_operator': 'AND',
                'conditions': [
                    {
                        'source_type': LogicCondition.SourceType.ASS,
                        'source_indicator': self.indicator.id,
                        'operator': '=',
                        'condition_type': 'any'
                    }
                ]
            }
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_create_indicator_standalone(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Standalone',
            'category': Indicator.Category.EVENTS,
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    
    def test_fail_options(self):
        '''
        Test out a couple types of indicators for an assessment.
        '''
        self.client.force_authenticate(user=self.admin)
        invalid_payload = {
            'name': 'Screened for NCDs',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.INT,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'options_data': [{'name': 'BMI'}, {'name': 'Blood Pressure'}, {'name': 'Blood Glucose'},],
            'allow_none': True,
            'logic_data': {}
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'name': 'Screened for NCDs',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.SINGLE,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'options_data': [],
            'allow_none': True,
            'logic_data': {}
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_aggregate_flag(self):
        '''
        Test out that various types/categories either do or do not accept the allow_aggregate flag.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'name': 'Valid 1',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.SINGLE,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'options_data': [{'name': 'BMI'}, {'name': 'Blood Pressure'}, {'name': 'Blood Glucose'},],
            'allow_none': True,
            'logic_data': {}
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        valid_payload = {
            'name': 'Valid 2',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.INT,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'options_data': [],
            'allow_none': True,
            'logic_data': {}
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        valid_payload = {
            'name': 'Valid 3',
            'category': Indicator.Category.MISC,
            'allow_aggregate': True,
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        invalid_payload = {
            'name': 'Invalid 1',
            'category': Indicator.Category.SOCIAL,
            'allow_aggregate': True, 
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'name': 'Invalid 2',
            'category': Indicator.Category.ASS,
            'type': Indicator.Type.TEXT,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'options_data': [],
            'allow_none': True,
            'logic_data': {}
        }
        response = self.client.post('/api/indicators/manage/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reorder(self):
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'position': 0
        }
        response = self.client.patch(f'/api/indicators/manage/{self.indicator_single.id}/change-order/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.indicator.refresh_from_db()
        self.indicator_int.refresh_from_db()
        self.indicator_txt.refresh_from_db()
        self.indicator_single.refresh_from_db()
        self.assertEqual(self.indicator_single.order, 0)
        self.assertEqual(self.indicator.order, 1)
        self.assertEqual(self.indicator_txt.order, 2)
        self.assertEqual(self.indicator_int.order, 3)

        invalid_payload = {
            'position': 8
        }
        response = self.client.patch(f'/api/indicators/manage/{self.indicator_single.id}/change-order/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'position': -1
        }
        response = self.client.patch(f'/api/indicators/manage/{self.indicator_single.id}/change-order/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    
    def test_create_not_admin(self):
        '''
        Other roles cannot create indicators.
        '''
        self.client.force_authenticate(user=self.officer)

        valid_payload = {
            'name': 'Test Assessment',
        }
        response = self.client.post('/api/indicators/assessments/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        valid_payload = {
            'name': 'Screened for NCDs',
            'type': Indicator.Type.MULTI,
            'category': Indicator.Category.ASS,
            'assessment_id': self.assessment.id,
            'allow_aggregate': True,
            'required': True,
            'options_data': [{'name': 'BMI'}, {'name': 'Blood Pressure'}, {'name': 'Blood Glucose'},],
            'allow_none': True,
            'logic_data': {}
        }
        response = self.client.post('/api/indicators/manage/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
   