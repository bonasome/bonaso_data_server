from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, ProjectOrganization
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, RespondentAttributeType
from organizations.models import Organization
from indicators.models import Indicator, Assessment, Option
from datetime import date
from flags.models import Flag
from flags.utils import create_flag

User = get_user_model()

class FlagViewSetTest(APITestCase):
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
        self.other = User.objects.create_user(username='other', password='testpass123', role='meofficer')
        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.admin.save()
        self.manager.organization = self.parent_org
        self.manager.save()
        self.officer.organization = self.child_org
        self.officer.save()
        self.data_collector.organization = self.parent_org
        self.data_collector.save()
        self.other.organization = self.other_org
        self.other.save()

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)

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

        self.child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        self.child_link.parent_organization = self.parent_org
        self.child_link.save()
        

         #simple assessment
        self.assessment = Assessment.objects.create(name='Ass')
        #general respondent indicators
        self.indicator = Indicator.objects.create(assessment=self.assessment, name='Select the Option', type=Indicator.Type.MULTI, allow_aggregate=True)
        self.option1 = Option.objects.create(name='Option 1', indicator=self.indicator)
        self.option2 = Option.objects.create(name='Option 2', indicator=self.indicator)
        self.indicator2 = Indicator.objects.create(assessment=self.assessment, name='Enter the Number', type=Indicator.Type.INT)

        self.task = Task.objects.create(project=self.project, organization=self.parent_org, assessment=self.assessment)
        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, assessment=self.assessment)
        self.other_task =Task.objects.create(project=self.project, organization=self.other_org, assessment=self.assessment)


        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

        self.interaction = Interaction.objects.create(interaction_date=self.today, interaction_location='there', respondent=self.respondent, task=self.task, created_by=self.data_collector)
        self.interaction_child = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, interaction_location='there',task=self.child_task, created_by=self.officer)
        self.interaction_other = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, interaction_location='there',task=self.other_task, created_by=self.other)

        flag = create_flag(self.interaction, "test_dc", self.data_collector)
        self.flag = Flag.objects.get(reason='test_dc')
        flag_resp = create_flag(self.respondent, "test_resp", self.admin)
        self.flag_resp = Flag.objects.get(reason='test_resp')
        flag_child = create_flag(self.interaction, "test_child", self.officer)
        self.flag_child = Flag.objects.get(reason='test_child')
        flag_other = create_flag(self.interaction, "test_other", self.other)
        self.flag_other = Flag.objects.get(reason='test_other')
        
    def test_flag_list_view(self):
        '''
        Test admins can see all.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/flags/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 4)
    
    def test_higher_role_list(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/flags/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_lower_role_list(self):
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/flags/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_raise_flag_valid(self):
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'model': 'respondents.interaction',
            'id': self.interaction.id,
            'reason': 'I dunno',
            'reason_type': Flag.FlagReason.SUS
        }
        response = self.client.post('/api/flags/raise-flag/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_raise_flag_child(self):
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'model': 'respondents.interaction',
            'id': self.interaction_child.id,
            'reason': 'I dunno',
            'reason_type': Flag.FlagReason.SUS
        }
        response = self.client.post('/api/flags/raise-flag/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_raise_flag_wrong_obj(self):
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'model': 'respondents.interaction',
            'id': self.interaction_other.id,
            'reason': 'I dunno',
        }
        response = self.client.post('/api/flags/raise-flag/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_raise_flag_perm(self):
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'model': 'respondents.interaction',
            'id': self.interaction.id,
            'reason': 'I dunno',
        }
        response = self.client.post('/api/flags/raise-flag/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_resolve_flag(self):
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
                    'resolved_reason': 'Nah man',
                }
        response = self.client.patch(f'/api/flags/{self.flag.id}/resolve-flag/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.resolved, True)
    
    def test_resolve_flag_child(self):
        self.client.force_authenticate(user=self.manager)
        
        valid_payload = {
                    'resolved_reason': 'Nah man',
                }
        response = self.client.patch(f'/api/flags/{self.flag_child.id}/resolve-flag/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.flag_child.refresh_from_db()
        self.assertEqual(self.flag_child.resolved, True)

    def test_resolve_flag_perm_fail(self):
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
                    'resolved_reason': 'Nah man',
                }
        response = self.client.patch(f'/api/flags/{self.flag_other.id}/resolve-flag/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
    
    