from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, ProjectOrganization
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, InteractionSubcategory, RespondentAttributeType
from organizations.models import Organization
from events.models import Event
from indicators.models import Indicator, IndicatorSubcategory
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
        
        self.planned_project = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )

        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.child_indicator = Indicator.objects.create(code='2', name='Child')
        self.child_indicator.prerequisites.set([self.indicator])
        self.not_in_project = Indicator.objects.create(code='3', name='Unrelated')
        
        self.req1 = RespondentAttributeType.objects.create(name='PLWHIV')
        self.req2 = RespondentAttributeType.objects.create(name='CHW')

        self.attr_indicator = Indicator.objects.create(code='5001', name='I NEED AN ATTRIBUTE')
        self.attr_indicator.required_attributes.set([self.req1, self.req2])

        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.prereq_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)
        self.attr_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.attr_indicator)
        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.indicator)
        self.other_task =Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator)

        self.inactive_task = Task.objects.create(project=self.planned_project, organization=self.parent_org, indicator=self.indicator)

        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
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

        self.interaction = Interaction.objects.create(interaction_date=self.today, interaction_location='there', respondent=self.respondent, task=self.task, created_by=self.data_collector)
        self.interaction2 = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent2, interaction_location='there',task=self.task, created_by=self.officer)
        self.interaction_child = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, interaction_location='there',task=self.child_task)
        self.interaction_other = Interaction.objects.create(interaction_date=self.today, respondent=self.respondent, interaction_location='there',task=self.other_task)

        self.event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-10',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task, self.child_task])
        self.event.organizations.set([self.parent_org, self.child_org])

        self.other_event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-10',
            location='here',
            host=self.other_org
        )
        self.other_event.organizations.set([self.other_org])
        self.other_event.tasks.set([self.other_task])

    def test_interaction_view(self):
        '''
        Interactions are public, and anyone is allowed to view them.
        '''
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get('/api/record/interactions/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 4)
    
    def test_create_interaction(self):
        '''
        Test a basic create payload, even though this style is rarely used in practiced.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.task.id,
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili',
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_interaction_child(self):
        '''
        M&E Officers and managers should have authority to create interactions for child orgs.
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'task_id': self.child_task.id, #task linked to a child organization
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili',
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_attach_event(self):
        '''
        A user can attach an interaction to a specific event.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.task.id, #task linked to a child organization
            'interaction_date': '2025-04-15',
            'interaction_location': 'That place that sells chili',
            'event_id': self.event.id,
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.task, interaction_date=date(2025, 4, 15)).first()
        self.assertEqual(ir.event.id, self.event.id)
    
    def test_attach_event_perms_associate(self):
        '''
        A user can attach an interaction to an event they are an associate with (i.e., attached child org).
        '''
        self.client.force_authenticate(user=self.officer)
        valid_payload = {
            'task_id': self.child_task.id, #task linked to a child organization
            'interaction_date': '2025-04-15',
            'interaction_location': 'That place that sells chili',
            'event_id': self.event.id,
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.child_task, interaction_date=date(2025, 4, 15)).first()
        self.assertEqual(ir.event.id, self.event.id)

    def test_attach_event_perms_wrong_event(self):
        '''
        A user can attach an interaction to an event they are an associate with (i.e., attached child org).
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'task_id': self.task.id, #task linked to a child organization
            'interaction_date': '2025-04-15',
            'interaction_location': 'That place that sells chili',
            'event_id': self.other_event.id,
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_dc_org_only(self):
        '''
        Lower ranks should only be allowed to create for their own organization.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.child_task.id,
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili',
            'respondent': self.respondent.id,
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
            'task_id': self.child_task.id,
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili',
            'respondent': self.respondent.id,
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
            'interaction_date': '2025-06-13',
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
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction2.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch__child_interaction_me_mgr(self):
        '''
        Higher ranks should have the ability to edit organizations from their children.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_child.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_patch_interaction_wrong_org(self):
        '''
        But not for other orgs.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'interaction_date': '2025-06-13',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_patch_interaction_bad_dates(self):
        '''
        Dates in the future or outside the project range should trigger a 400. Bad dates should also
        trigger a 400.
        '''
        self.client.force_authenticate(user=self.admin)
        tomorrow = date.today() + timedelta(days=1)
        invalid_payload = {
            'interaction_date': tomorrow,
        }
        #date can't be in the future
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        
        invalid_payload = {
            'interaction_date': '2024-06-02',
        }
        #date can't be in the future
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', invalid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        invalid_payload = {
            'interaction_date': '2025-063-p',
        }
        response = self.client.patch(f'/api/record/interactions/{self.interaction_other.id}/', invalid_payload, format='json')
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
    
    def test_delete_interaction_prereq(self):
        '''
        If an interaction has a downstream interaction (other interaction using it as a prerequisite) it should not
        be deleteable.
        '''
        interaction_child = Interaction.objects.create(respondent=self.respondent, task=self.prereq_task, interaction_date=self.today)
        self.client.force_authenticate(user=self.admin)
        response = self.client.delete(f'/api/record/interactions/{self.interaction.id}/')
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

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
        

    def test_create_attr(self):
        '''
        If an interaction's indicator requires a special attribute and the respondent does not have
        that attribute, the interaction will be flagged. It should also be resolved automatically.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.attr_task.id,
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.attr_task, respondent=self.respondent3).first()
        self.assertEqual(ir.flags.count(), 2)
        print(response.json())

        self.respondent3.special_attribute.set([self.req1]) #set one attribute
        self.respondent3.refresh_from_db()
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'interaction_date': '2025-06-15',
        } #trigger the function again with a patch
        response = self.client.patch(f'/api/record/interactions/{ir.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ir.refresh_from_db()
        self.assertEqual(ir.flags.filter(resolved=False).count(), 1)
        print(response.json())

        self.respondent3.special_attribute.set([self.req1, self.req2]) #set both
        self.respondent3.refresh_from_db()
        response = self.client.patch(f'/api/record/interactions/{ir.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK) 
        print(response.json())
        ir.refresh_from_db()
        self.assertEqual(ir.flags.filter(resolved=False).count(), 0) #run again and it should be fine
        

    def test_create_no_prereq(self):
        '''
        Interactions that do not have a prerequisite interaction should get flagged automatically. If a prerequisite
        interaction is created, then it should be automatically resolved.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.prereq_task.id,
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.prereq_task, respondent=self.respondent3).first()
        self.assertEqual(ir.flags.count(), 1)
        flag = ir.flags.first()
        self.assertIn('to have a valid interaction with this respondent within the past year', flag.reason)

        #upload prereq and it should be fine now
        valid_payload = {
            'task_id': self.task.id,
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.prereq_task, respondent=self.respondent3).first()
        os_flags = ir.flags.filter(resolved=False)
        self.assertEqual(os_flags.count(), 0)

        res_flags = ir.flags.filter(resolved=True)
        self.assertEqual(res_flags.count(), 1)
        flag = res_flags.first()
        self.assertEqual(flag.auto_resolved, True)

    def test_create_prereq_dates(self):
        '''
        Misaligned dates should raise a flag (prereq after its dependent)
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.task.id,
            'interaction_date': '2025-06-15',
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        #prereq has task, but date is before
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_id': self.prereq_task.id,
            'interaction_date': '2025-06-12',
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.prereq_task, respondent=self.respondent3).first()
        self.assertEqual(ir.flags.count(), 1)
        flag = ir.flags.first()
        self.assertIn('Make sure the prerequisite interaction is not in the future.', flag.reason)

        #update with proper date
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'interaction_date': '2025-06-15',
        }
        response = self.client.patch(f'/api/record/interactions/{ir.id}/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        os_flags =ir.flags.filter(resolved=False)
        self.assertEqual(os_flags.count(), 0)

        res_flags = ir.flags.filter(resolved=True)
        self.assertEqual(res_flags.count(), 1)
        flag = res_flags.first()
        self.assertEqual(flag.auto_resolved, True)

    
    def test_create_interaction_prereq_subcats(self):
        '''
        Non subset with matching subcats should raise a flag.
        '''
        self.client.force_authenticate(user=self.data_collector)
        ind1 = Indicator.objects.create(code='10', name='ParentSubcat')
        ind2 = Indicator.objects.create(code='11', name='ChildSubcat', match_subcategories_to=ind1)
        ind2.prerequisites.set([ind1])
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind1.subcategories.set([category, category2])
        ind2.subcategories.set([category, category2])

        task_parent = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind1)
        task_child = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind2)

        #categories are wrong, so it should fail
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent.id,
            'task_id': task_parent.id,
            'subcategories_data': [{'id': None, 'subcategory': {'name': 'Cat 1', 'id': category.id}}]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent.id,
            'task_id': task_child.id,
            'subcategories_data': [{'id': None, 'subcategory': {'name': 'Cat 1', 'id': category.id}}, {'id': None, 'subcategory': {'name': 'Cat 2', 'id': category2.id}}]
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        ir = Interaction.objects.filter(task=task_child, respondent=self.respondent).first()
        flags = ir.flags.filter(resolved=False)
        self.assertEqual(flags.count(), 1)
        flag = flags.first()
        self.assertIn('This interaction will be flagged until the subcategories match.', flag.reason)

        #update with matched categories
        response = self.client.patch(f'/api/record/interactions/{ir.id}/', {
            'subcategories_data': [{'id': None, 'subcategory': {'name': 'Cat 1', 'id': category.id}}]
        }, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        os_flags = ir.flags.filter(resolved=False)
        self.assertEqual(os_flags.count(), 0)

        res_flags = ir.flags.filter(resolved=True)
        self.assertEqual(res_flags.count(), 1)
        flag = res_flags.first()
        self.assertEqual(flag.auto_resolved, True)
    
    def test_create_interaction_forgot_subcats(self):
        self.client.force_authenticate(user=self.data_collector)
        ind1 = Indicator.objects.create(code='10', name='GimmeDemSubcats')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        ind1.subcategories.set([category])
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind1)
        valid_payload = {
            'task_id': task.id,
            'interaction_location': 'That place that sells chili.',
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #try again with subcats
        valid_payload = {
            'task_id': task.id,
            'interaction_location': 'That place that sells chili.',
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
            'subcategories_data': [{'id': None, 'subcategory': {'name': 'Cat 1', 'id': category.id}}]
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_interaction_forgot_number(self):
        '''
        Lack of a number should trigger a 400.
        '''
        self.client.force_authenticate(user=self.data_collector)
        ind = Indicator.objects.create(code='10', name='GimmeANummie', require_numeric=True)
        task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind)
        valid_payload = {
            'task_id': task.id,
            'interaction_location': 'That place that sells chili.',
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #not quite there
        valid_payload = {
            'task_id': task.id,
            'interaction_location': 'That place that sells chili.',
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
            'numeric_component': 'oops I forgot the number'
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        #there we go
        valid_payload = {
            'task_id': task.id,
            'interaction_location': 'That place that sells chili.',
            'interaction_date': '2025-06-15',
            'respondent': self.respondent3.id,
            'numeric_component': 5
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_interaction_numeric_subcats(self):
        self.client.force_authenticate(user=self.admin)
        ind = Indicator.objects.create(code='10', name='GimmeANummieANDDatSubcat', require_numeric=True)
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind.subcategories.set([category, category2])
        task_numsub = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind)
        response = self.client.post('/api/record/interactions/', {
            'interaction_date': self.today,
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent.id,
            'task_id': task_numsub.id,
            'subcategories_data': [{'id':None, 'subcategory': {'name': 'Cat 1', 'id': category.id}, 'numeric_component': 5}, {'id': None, 'subcategory': {'name': 'Cat 2', 'id': category2.id}, 'numeric_component': 10}]
        }, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.get(task=task_numsub, respondent=self.respondent.id)
        self.assertEqual(ir.subcategories.count(), 2)
        irsc1 = InteractionSubcategory.objects.get(subcategory=category, interaction=ir)
        irsc2 = InteractionSubcategory.objects.get(subcategory=category2, interaction=ir)
        self.assertEqual(irsc1.numeric_component, 5)
        self.assertEqual(irsc2.numeric_component, 10)

    def test_bulk_create(self):
        self.client.force_authenticate(user=self.data_collector)
        
        ind_number = Indicator.objects.create(code='4', name='Numeric Ind', require_numeric=True)
        ind_subcat = Indicator.objects.create(code='10', name='GimmeDemSubcats')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind_subcat.subcategories.set([category, category2])
        
        task_number = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_number)
        task_subcat = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat)
        
        response = self.client.post('/api/record/interactions/batch/', {
            'interaction_date': date(2025, 6, 1),
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
            'tasks': [
                {'task_id': self.task.id},
                {'task_id': task_number.id, 'numeric_component': 10},
                {'task_id': task_subcat.id, 'subcategories_data': [{'id': None, 'subcategory': {'name': 'Cat 1', 'id': category.id}}, {'id': None, 'subcategory': {'name': 'Cat 2', 'id': category2.id}}]}
            ]
        }, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_bulk_create_edge(self):
        self.client.force_authenticate(user=self.data_collector)
        
        ind_number = Indicator.objects.create(code='4', name='Numeric Ind', require_numeric=True)
        ind_subcat = Indicator.objects.create(code='10', name='GimmeDemSubcats')
        ind_subcat_prereq = Indicator.objects.create(code='11', name='GimmeDemSubcatsV2')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind_subcat.subcategories.set([category, category2])
        ind_subcat_prereq.subcategories.set([category, category2])
        task_number = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_number)
        task_subcat = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat)
        task_subcat_prereq = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat_prereq)
        response = self.client.post('/api/record/interactions/batch/', {
            'interaction_date': date(2025, 6, 1),
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
            'tasks': [
                {'task_id': self.task.id},
                {'task_id': task_number.id, 'numeric_component': 10},
                {'task_id': task_subcat_prereq.id, 'subcategories_data': [{'id': None, 'subcategory': {'name': 'Cat 1', 'id': category.id}}, {'id': None, 'subcategory': {'name': 'Cat 2', 'id': category2.id}}]},
                {'task_id': task_subcat.id, 'subcategories_data': [{'id': None, 'subcateogry': {'name': 'Cat 1', 'id': category.id}}, {'id': None, 'subcategory': {'name': 'Cat 2', 'id': category2.id}}]}
            ]
        }, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_bulk_create_client(self):
        self.client.force_authenticate(user=self.client_user)
        
        ind_number = Indicator.objects.create(code='4', name='Numeric Ind', require_numeric=True)
        ind_subcat = Indicator.objects.create(code='10', name='GimmeDemSubcats')
        ind_subcat_prereq = Indicator.objects.create(code='11', name='GimmeDemSubcatsV2')
        category = IndicatorSubcategory.objects.create(name='Cat 1')
        category2 = IndicatorSubcategory.objects.create(name='Cat 2')
        ind_subcat.subcategories.set([category, category2])
        ind_subcat_prereq.subcategories.set([category, category2])
        task_number = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_number)
        task_subcat = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat)
        task_subcat_prereq = Task.objects.create(project=self.project, organization=self.parent_org, indicator=ind_subcat_prereq)
        response = self.client.post('/api/record/interactions/batch/', {
            'interaction_date': date(2025, 6, 1),
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent3.id,
            'tasks': [
                {'task_id': self.task.id},
                {'task_id': task_number.id, 'numeric_component': 10},
            ]
        }, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)