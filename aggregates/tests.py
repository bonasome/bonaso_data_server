from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

from aggregates.models import AggregateCount, AggregateGroup
from projects.models import Project, Client, Task, ProjectOrganization
from organizations.models import Organization
from indicators.models import Indicator, Assessment, LogicCondition, LogicGroup, Option

User = get_user_model()

class AggregatesTest(APITestCase):
    '''
    Primarily a test of the counts viewset.
    '''
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
        self.view_user = User.objects.create(username='uninitiated', password='testpass', role='view_only')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org
        self.view_user.organization = self.parent_org

        self.client_user.organization = self.other_org

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.other_client_obj = Client.objects.create(name='Loser Client', created_by=self.admin)

        self.client_user.client_organization = self.client_obj
        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent_org, self.other_org, self.child_org])

        child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        child_link.parent_organization = self.parent_org
        child_link.save()

        #generic assessment mocking a screened referred with options
        self.assessment = Assessment.objects.create(name='Ass.')
        
        self.indicator = Indicator.objects.create(name='Screened for Thing', allow_aggregate=True, type=Indicator.Type.MULTI, assessment=self.assessment)
        self.option1 = Option.objects.create(name='Option 1', indicator=self.indicator)
        self.option2 = Option.objects.create(name='Option 2', indicator=self.indicator)
        self.indicator2 = Indicator.objects.create(name='Screened for Thing', allow_aggregate=True, type=Indicator.Type.MULTI, match_options=self.indicator, assessment=self.assessment)
        
        self.group_a = LogicGroup.objects.create(indicator=self.indicator2)
        self.conditon_a = LogicCondition.objects.create(group=self.group_a, source_indicator=self.indicator, condition_type='any')
        
        self.task = Task.objects.create(assessment=self.assessment, project=self.project, organization=self.parent_org)
        self.child_task = Task.objects.create(assessment=self.assessment, project=self.project, organization=self.child_org)
        
        #create a bool for testing too
        self.bool_indicator = Indicator.objects.create(name='Tested Positive', allow_aggregate=True, type=Indicator.Type.BOOL, assessment=self.assessment)


        self.ind_no_agg = Indicator.objects.create(name='Whatever you do, dont aggregate this', category=Indicator.Category.MISC, allow_aggregate=False)
        self.task_no_agg = Task.objects.create(indicator=self.ind_no_agg, project=self.project, organization=self.parent_org)

    def test_count_creation_options(self):
        '''
        Test a basic count creation
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 5,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option2.id,
                },
                {
                    'value': 27,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        group = AggregateGroup.objects.filter(start='2025-01-01', end='2025-01-03').first()
        counts = AggregateCount.objects.filter(group=group)
        check_val = counts.filter(option=self.option2).first()
        check_total_val = counts.filter(unique_only=True).first()
        self.assertEqual(counts.count(), 3)
        self.assertEqual(check_val.value, 5)
        self.assertEqual(check_total_val.value, 27)
        self.assertEqual(check_val.created_by, self.admin)
    
    def test_count_creation_no_options(self):
        '''
        Test a basic count creation (boolean)
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.bool_indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 50,
                    'sex': 'M',
                    'age_range': '20_24',
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        check_val = AggregateCount.objects.filter(group__indicator=self.bool_indicator).first()
        self.assertEqual(check_val.value, 50)
    
    def test_duplicate_rows(self):
        '''
        Make sure a user can't submit "duplicate" rows (same breakdowns)
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'option_id': self.option1.id,
                },
                {
                    'value': 26,
                    'disability_type': 'VI',
                    'option_id': self.option1.id,
                },
                {
                    'value': 26,
                    'disability_type': 'VI',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_option_req(self):
        '''
        Make sure that if an indicator has options, the user is sending data for those
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_option_total_req(self):
        '''
        Make sure that if an indicator is multiselect, user is sending a total flag
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'option_id': self.option1.id
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_option_total_valid(self):
        '''
        Make sure that if an indicator is multiselect, user is sending a total flag that is equal
        to the smallest option
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 29,
                    'disability_type': 'VI',
                    'option_id': self.option1.id
                },
                {
                    'value': 28,
                    'disability_type': 'VI',
                    'unique_only': True
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_rogue_option(self):
        '''
        Make sure that if an indicator has options, the user is sending data for those.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.bool_indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'option_id': self.option1.id
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_future(self):
        '''
        A count should not be able to be created in the future (an end in the future is ok, but the start
        must be in the past).
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2067-01-05', 
            'end': '2067-01-07',
            'counts_data': [
                {
                    'value': 25,
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'unique_only': True,
                },
            ]
        }

        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_start_after_end(self):
        '''
        A count should not be able to be created if the start date is after the end date.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-07', 
            'end': '2025-01-01',
            'counts_data': [
                {
                    'value': 25,
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'unique_only': True,
                },
            ]
        }

        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_count_logic(self):
        '''
        Test that flags are created if logic applies and is not met.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator2.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-03',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        count = AggregateCount.objects.filter(group__indicator=self.indicator2).first()
        self.assertEqual(count.flags.count(), 1)
        self.assertIn('requires a corresponding count', count.flags.filter(resolved=False).first().reason)

        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 20,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 20,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.prereq_count = AggregateCount.objects.filter(group__indicator=self.indicator).first()


        self.assertEqual(count.flags.filter(resolved=False).count(), 1)
        self.assertIn('higher than the corresponding value', count.flags.filter(resolved=False).first().reason)

        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.patch(f'/api/aggregates/{self.prereq_count.group.id}/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        self.assertEqual(count.flags.filter(resolved=True).count(), 2)
        self.assertEqual(count.flags.filter(resolved=False).count(), 0)
    

    def test_no_task(self):
        '''
        Can't create a count for a task that doesn't exist. 
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.other_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_agg_not_allowed(self):
        '''
        Can't create a count for an indicator that does not allow aggregates.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'indicator_id': self.ind_no_agg.id,
            'organization_id': self.other_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_count_perm(self):
        '''
        A manager should be able to edit counts for their own tasks and their children.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        #should also work
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.child_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_perm_fail_wrong_org(self):
        '''
        but not for an unrelated org
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.other_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_perm_fail_dc(self):
        '''
        Data collectors cannot create aggregates.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'indicator_id': self.indicator.id,
            'organization_id': self.parent_org.id,
            'project_id': self.project.id,
            'start': '2025-01-01',
            'end': '2025-01-02',
            'counts_data': [
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'option_id': self.option1.id,
                },
                {
                    'value': 25,
                    'disability_type': 'VI',
                    'kp_type': 'MSM',
                    'pregnancy': 'pregnant',
                    'hiv_status': 'hiv_positive',
                    'sex': 'M',
                    'age_range': '20_24',
                    'citizenship': 'citizen',
                    'unique_only': True,
                },
            ]
        }
        response = self.client.post(f'/api/aggregates/', valid_payload, content_type='application/json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

