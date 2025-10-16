from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, ProjectOrganization
from respondents.models import Respondent, Interaction, RespondentAttributeType, Response
from organizations.models import Organization
from indicators.models import Indicator, Assessment, LogicCondition, Option, LogicGroup
from datetime import date, timedelta
User = get_user_model()

class InteractionViewSetTest(APITestCase):
    '''
    Test the interaction serializer and make sure the perms work and that the flagging system works.
    '''
    def setUp(self):
        self.today = date.today().isoformat()

        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org
        self.client_user.organization = self.parent_org

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.other_client_obj = Client.objects.create(name='Loser Client', created_by=self.admin)
        self.client_user.client_organization = self.client_obj
        
        # set up a project
        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2025-01-01',
            end='2025-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent_org, self.child_org, self.other_org])
        #child orgs for project
        self.child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        self.child_link.parent_organization = self.parent_org
        self.child_link.save()

        #setup a simple assessment we can use for patching/fetching
        self.assessment_exists = Assessment.objects.create(name='Exists')
        self.indicator_exists = Indicator.objects.create(name='You answered this', assessment=self.assessment_exists, type=Indicator.Type.BOOL)
        self.indicator_exists2 = Indicator.objects.create(name='Right?', assessment=self.assessment_exists, type=Indicator.Type.BOOL)
        self.exists_group= LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_exists2)
        self.exists_condition = LogicCondition.objects.create(group=self.exists_group, source_indicator=self.indicator_exists, source_type=LogicCondition.SourceType.ASS, operator=LogicCondition.Operator.EQUALS, value_boolean=True)
        
        # and related tasks
        self.task_exists = Task.objects.create(project=self.project, organization=self.parent_org, assessment=self.assessment_exists)
        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, assessment=self.assessment_exists)
        self.other_task =Task.objects.create(project=self.project, organization=self.other_org, assessment=self.assessment_exists)
        
        #set up respondent
        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.MALE,
        )
        self.respondent2= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        self.respondent3= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        self.req1 = RespondentAttributeType.objects.create(name='PLWHIV')
        self.req2 = RespondentAttributeType.objects.create(name='CHW')

        #set up dummy interaction with assessment_exists
        self.interaction = Interaction.objects.create(interaction_date=self.today, interaction_location='there', respondent=self.respondent, task=self.task_exists, created_by=self.data_collector)
        self.response1 = Response.objects.create(interaction=self.interaction, response_date=self.today, response_location='there', indicator=self.indicator_exists, response_boolean=True)
        self.response2 = Response.objects.create(interaction=self.interaction,response_date=self.today, response_location='there', indicator=self.indicator_exists, response_boolean=False)
        
        #set up a test with child org for perms
        self.interaction_child = Interaction.objects.create(interaction_date=self.today, interaction_location='there', respondent=self.respondent2, task=self.task_exists, created_by=self.data_collector)
        self.response_child1 = Response.objects.create(interaction=self.interaction_child,response_date=self.today, response_location='there', indicator=self.indicator_exists, response_boolean=True)
        self.response_child2 = Response.objects.create(interaction=self.interaction_child,response_date=self.today, response_location='there', indicator=self.indicator_exists, response_boolean=False)
        
        #and other org
        self.interaction_other = Interaction.objects.create(interaction_date=self.today, interaction_location='there', respondent=self.respondent3, task=self.task_exists, created_by=self.data_collector)
        self.response_other1 = Response.objects.create(interaction=self.interaction_child,response_date=self.today, response_location='there', indicator=self.indicator_exists, response_boolean=True)
        self.response_other2 = Response.objects.create(interaction=self.interaction_child,response_date=self.today, response_location='there', indicator=self.indicator_exists, response_boolean=False)

        #set up the main assessment
        self.assessment = Assessment.objects.create(name='ass')
        
        #start with a multiselect
        self.indicator_1 = Indicator.objects.create(name='Screened for NCDs', assessment=self.assessment, type=Indicator.Type.MULTI, required=True)
        self.option1= Option.objects.create(name='BMI', indicator=self.indicator_1)
        self.option2= Option.objects.create(name='Blood Pressure', indicator=self.indicator_1)
        self.option3= Option.objects.create(name='Blood Glucose', indicator=self.indicator_1)
        #int, only visible if option2 is selected
        self.indicator_1_1 = Indicator.objects.create(name='Blood Pressure Reading', assessment=self.assessment, type=Indicator.Type.INT, required=False)
        self.g11 = LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_1_1)
        self.c111 = LogicCondition.objects.create(group=self.g11, source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_1, value_option=self.option2, operator=LogicCondition.Operator.EQUALS)
        #visible if any of ind1 is selected, matches options
        self.indicator_2 = Indicator.objects.create(name='Referred for NCDs', assessment=self.assessment, type=Indicator.Type.MULTI, allow_none=True, match_options=self.indicator_1, required=True)
        self.g2 = LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_2)
        self.c21 = LogicCondition.objects.create(group=self.g2,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_1, condition_type=LogicCondition.ExtraChoices.ANY, operator=LogicCondition.Operator.EQUALS)

        #visible if ind 2 is option 2 OR 3
        self.indicator_3 = Indicator.objects.create(name='What Blood Treatment Referred', assessment=self.assessment, type=Indicator.Type.SINGLE, required=True)
        self.option4= Option.objects.create(name='Treatment 1', indicator=self.indicator_3)
        self.option5= Option.objects.create(name='Treatment 2', indicator=self.indicator_3)
        self.g3 = LogicGroup.objects.create(group_operator='OR', indicator=self.indicator_3)
        self.c31 = LogicCondition.objects.create(group=self.g3, source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_2, value_option=self.option2, operator=LogicCondition.Operator.EQUALS)
        self.c32 = LogicCondition.objects.create(group=self.g3,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_2, value_option=self.option3, operator=LogicCondition.Operator.EQUALS)
        # visible if ind 2 is option1 and ind 3 is option5 and respondent is male
        self.indicator_4 = Indicator.objects.create(name='Treatment 2 for BMI?', assessment=self.assessment, type=Indicator.Type.BOOL, required=True)
        self.g4 = LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_4)
        self.c41 = LogicCondition.objects.create(group=self.g4,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_2, value_option=self.option1, operator=LogicCondition.Operator.EQUALS)
        self.c42 = LogicCondition.objects.create(group=self.g4,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_3, value_option=self.option5, operator=LogicCondition.Operator.EQUALS)
        self.c43 = LogicCondition.objects.create(group=self.g4,source_type=LogicCondition.SourceType.RES, respondent_field='sex', value_text='M', operator=LogicCondition.Operator.EQUALS)

        # visible if 4 is trie
        self.indicator_5 = Indicator.objects.create(name='Number of Sessions Needed', assessment=self.assessment, type=Indicator.Type.INT, required=True)
        self.g5 = LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_5)
        self.c51 = LogicCondition.objects.create(group=self.g5,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_4, value_boolean=True)

        #visible if 5 is greater than 5
        self.indicator_6 = Indicator.objects.create(name='Reason for Number > 5', assessment=self.assessment, type=Indicator.Type.TEXT, required=True)
        self.g6 = LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_6)
        self.c61 = LogicCondition.objects.create(group=self.g6,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_5, value_text=5, operator=LogicCondition.Operator.GT)

        #visible if 6 contains secret and not loser
        self.indicator_7 = Indicator.objects.create(name='You found the secret!', assessment=self.assessment, type=Indicator.Type.TEXT, required=True)
        self.g7 = LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_7)
        self.c71 = LogicCondition.objects.create(group=self.g7, source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_6, value_text='secret', operator=LogicCondition.Operator.C)
        self.c71 = LogicCondition.objects.create(group=self.g7,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_6, value_text='loser', operator=LogicCondition.Operator.DNC)
        
        self.task = Task.objects.create(project=self.project, organization=self.parent_org, assessment=self.assessment)

        #simple test for none
        self.assessment_none = Assessment.objects.create(name='None')
        
        self.indicator_none_mult = Indicator.objects.create(name='Screened for NCDs', assessment=self.assessment_none, type=Indicator.Type.MULTI, required=True, allow_none=True)
        self.option_none= Option.objects.create(name='Option 1 None', indicator=self.indicator_none_mult)
        self.option_none2= Option.objects.create(name='Option 2 None', indicator=self.indicator_none_mult)
        # should only appear if none_nult was ['none]
        self.indicator_none_mult_log = Indicator.objects.create(name='Why not?', assessment=self.assessment_none, type=Indicator.Type.TEXT, required=True)
        self.g2_none = LogicGroup.objects.create(group_operator='AND', indicator=self.indicator_none_mult_log)
        self.c21_none = LogicCondition.objects.create(group=self.g2_none,source_type=LogicCondition.SourceType.ASS, source_indicator=self.indicator_none_mult, condition_type=LogicCondition.ExtraChoices.NONE, operator=LogicCondition.Operator.EQUALS)

        self.task_none = Task.objects.create(project=self.project, organization=self.parent_org, assessment=self.assessment_none)

    def test_create_ir(self):
        '''
        Test a successful creation of an interaction (using lowest perms), and make sure that all logic
        passes.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.task.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_1.id: {
                    'value': [self.option1.id, self.option2.id],
                },
                self.indicator_1_1.id: {
                    'value': '',
                },
                self.indicator_2.id: {
                    'value': [self.option1.id, self.option2.id],
                },
                self.indicator_3.id: {
                    'value': self.option5.id,
                },
                self.indicator_4.id: {
                    'value': True,
                },
                self.indicator_5.id: {
                    'value': 6,
                },
                self.indicator_6.id: {
                    'value': 'secret tt',
                },
                self.indicator_7.id: {
                    'value': 'Yay!',
                    'date': '2025-01-02',
                    'location': 'Here'
                },
            }
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.task).first()
        answers = Response.objects.filter(interaction=ir)
        self.assertEqual(answers.count(), 9) # 1_1 should not be filled since it was not required, +2 for extra options
        
        #confirm that all values are correct
        sing = answers.filter(indicator=self.indicator_3).first()
        self.assertEqual(sing.response_option, self.option5)
        multi = answers.filter(indicator=self.indicator_1)
        self.assertEqual(multi.count(), 2)

        boolA = answers.filter(indicator=self.indicator_4).first()
        self.assertEqual(boolA.response_boolean, True)
        num = answers.filter(indicator=self.indicator_5).first()
        self.assertEqual(num.response_value, '6')
        txt = answers.filter(indicator=self.indicator_6).first()
        self.assertEqual(txt.response_value, 'secret tt')
        secret = answers.filter(indicator=self.indicator_7).first()
        self.assertEqual(secret.response_date, date(2025, 1, 2))
        self.assertEqual(secret.response_location, 'Here')

    def test_bad_logic(self):
        '''
        Confirm that logic flags when it's supposed to.
        '''
        self.client.force_authenticate(user=self.data_collector)
        #should fail since 1_1 needs option2
        invalid_payload = {
            'task_id': self.task.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_1.id: {
                    'value': [self.option1.id],
                },
                self.indicator_1_1.id: {
                    'value': '70',
                },
                self.indicator_2.id: {
                    'value': [self.option1.id],
                },
            }
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('logic_error', data)
        self.assertIn(f'Indicator {self.indicator_1_1.name} does not meet the criteria to be answered.', data['logic_error'])
        
        # 7 should fail since 6 contains text "loser"
        invalid_payload = {
            'task_id': self.task.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_1.id: {
                    'value': [self.option1.id, self.option2.id],
                },
                self.indicator_1_1.id: {
                    'value': '',
                },
                self.indicator_2.id: {
                    'value': [self.option1.id, self.option2.id],
                },
                self.indicator_3.id: {
                    'value': self.option5.id,
                },
                self.indicator_4.id: {
                    'value': True,
                },
                self.indicator_5.id: {
                    'value': 6,
                },
                self.indicator_6.id: {
                    'value': 'secret loser',
                },
                self.indicator_7.id: {
                    'value': 'Yay!',
                },
            }
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('logic_error', data)
        self.assertIn(f'Indicator {self.indicator_7.name} does not meet the criteria to be answered.', data['logic_error'])

        # 4 should fail since respondent is female
        invalid_payload = {
            'task_id': self.task.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_1.id: {
                    'value': [self.option1.id, self.option2.id],
                },
                self.indicator_1_1.id: {
                    'value': '',
                },
                self.indicator_2.id: {
                    'value': [self.option1.id, self.option2.id],
                },
                self.indicator_3.id: {
                    'value': self.option5.id,
                },
                self.indicator_4.id: {
                    'value': True,
                },
            }
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('logic_error', data)
        self.assertIn(f'Indicator {self.indicator_4.name} does not meet the criteria to be answered.', data['logic_error'])

    def test_none_logic(self):
        '''
        Test logic for none operators, since this is where it can get a little weird.
        '''
        self.client.force_authenticate(user=self.data_collector)
        #OK, mult was ['none'] and log is filled
        valid_payload = {
            'task_id': self.task_none.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_none_mult.id: {
                    'value': ['none'],
                },
                self.indicator_none_mult_log.id: {
                    'value': 'Huh?',
                },
            }
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        #not ok, since mult was not none, something was selected, no value should be present for log
        invalid_payload = {
            'task_id': self.task_none.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_none_mult.id: {
                    'value': [self.option_none.id],
                },
                self.indicator_none_mult_log.id: {
                    'value': 'Huh?',
                },
            }
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        print(response.json())
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('logic_error', data)
        self.assertIn(f'Indicator {self.indicator_none_mult_log.name} does not meet the criteria to be answered.', data['logic_error'])

    def test_mismatched_options(self):
        '''
        If an indicator has matched options with another, that indicator should not have 
        selected options that were not selected for the indicator it was matched with.
        '''
        self.client.force_authenticate(user=self.data_collector)

        #should fail, 2 is matched with 1 and 2 has options 1 does not
        invalid_payload = {
            'task_id': self.task.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_1.id: {
                    'value': [self.option1.id],
                },
                self.indicator_2.id: {
                    'value': [self.option1.id, self.option2.id],
                },
                self.indicator_3.id: {
                    'value': self.option4.id,
                },
            }
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', data)
        self.assertIn(f'Values for "{self.indicator_2.name}" must be a subset of the values provided for "{self.indicator_1.name}".', data['non_field_errors'])

    def test_missing_req(self):
        '''
        If an indicator is required, data for it is needed (the indicator must be present and it must have a value)
        '''
        self.client.force_authenticate(user=self.data_collector)

        #missing 1
        invalid_payload = {
            'task_id': self.task.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_2.id: {
                    'value': [self.option1.id],
                },
            }
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        print(response.json())
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', data)
        self.assertIn(f'Indicator {self.indicator_1.name} is required.', data['non_field_errors'])

        #1 is an empty array (nothing selected)
        invalid_payload = {
            'task_id': self.task.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_1.id: {
                    'value': [],
                },
                self.indicator_2.id: {
                    'value': [self.option1.id],
                },
            }
        }
        response = self.client.post('/api/record/interactions/', invalid_payload, format='json')
        data = response.json()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', data)
        self.assertIn(f'Indicator {self.indicator_1.name} is required.', data['non_field_errors'])

    def test_interaction_view(self):
        '''
        Interactions are public, and anyone is allowed to view them.
        '''
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    
    def test_create_interaction_child(self):
        '''
        M&E Officers and managers should have authority to create interactions for child orgs.
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'task_id': self.child_task.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


    def test_dc_org_only(self):
        '''
        Lower ranks should only be allowed to create for their own organization.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.child_task.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_interaction_client(self):
        '''
        Clients should be disbarred from creating any interactions.
        '''
        self.client.force_authenticate(user=self.client_user)
        valid_payload = {
            'task_id': self.task_exists.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_interaction(self):
        '''
        Lower ranks should be allowed to patch their own interactions (fix flags, correct mistakes.)
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.task_exists.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_patch_interaction_no_perm(self):
        '''
        But lower ranks cannot patch interactions they did not create, even if they are within the same organization.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.child_task.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_interaction_wrong_org(self):
        '''
        M&E should not be able to patch for other orgs
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'task_id': self.other_task.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_interaction_bad_logic(self):
        '''
        Patches should also pick logic errors.
        '''
        self.client.force_authenticate(user=self.data_collector)
        #exists 2 needs exists to be true
        invalid_payload = {
            'task_id': self.task_exists.id,
            'respondent_id': self.respondent.id,
            'interaction_date': '2025-01-01',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':False,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction.id}/', invalid_payload, format='json')
        data = response.json()
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('logic_error', data)
        self.assertIn(f'Indicator {self.indicator_exists2.name} does not meet the criteria to be answered.', data['logic_error'])

    def test_patch_interaction_bad_dates(self):
        '''
        Dates in the future or outside the project range should trigger a 400. Bad dates should also
        trigger a 400.
        '''
        self.client.force_authenticate(user=self.admin)
        tomorrow = date.today() + timedelta(days=1)
        invalid_payload = {
            'task_id': self.task_exists.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': tomorrow,
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        #date can't be in the future
        response = self.client.post(f'/api/record/interactions/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'task_id': self.task_exists.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2022-01-02',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                },
            }
        }
        #date can't be in the future
        response = self.client.post(f'/api/record/interactions/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'task_id': self.task_exists.id,
            'respondent_id': self.respondent2.id,
            'interaction_date': '2025-01-02',
            'interaction_location': 'There',
            'response_data': {
                self.indicator_exists.id: {
                    'value':True,
                },
                self.indicator_exists2.id: {
                    'value': True,
                    'date': '2021-01-06'
                },
            }
        }
        #date can't be in the future
        response = self.client.post(f'/api/record/interactions/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


    def test_delete_interaction(self):
        '''
        Admins are allowed the delete interactions, but this is not encouraged behavior. There is a flagging system.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/record/interactions/{self.interaction_other.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_interaction_no_perm(self):
        '''
        No one else is allowed to delete.
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.delete(f'/api/record/interactions/{self.interaction.id}/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    

    def test_flag_too_close(self):
        '''
        If not disabled, interactions with the same respondent/task within 30 days should trigger a flag
        for review.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 5),
            'interaction_location': 'That place that sells chili',
            'respondent': self.respondent3.id,
            'task_id': self.task.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        ir = Interaction.objects.get(interaction_date=date(2025, 6, 5), task=self.task, respondent=self.respondent3)
        self.assertEqual(ir.flags.count(), 0)
        
        
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': date(2025, 6, 7),
            'interaction_location': 'That place that sells chili',
            'respondent': self.respondent3.id,
            'task_id': self.task.id
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_ir = Interaction.objects.get(interaction_date=date(2025, 6, 7), task=self.task, respondent=self.respondent3)
        self.assertEqual(new_ir.flags.count(), 1)
        flag = new_ir.flags.first()
        self.assertIn('within 30 days of this interaction', flag.reason)