from django.test import TestCase
from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import Q

from projects.models import Project, Client, Task, ProjectOrganization
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, InteractionSubcategory
from events.models import Event, DemographicCount
from social.models import SocialMediaPost
from organizations.models import Organization
from events.models import Event
from indicators.models import Indicator
from datetime import date, timedelta
from flags.utils import create_flag
User = get_user_model()

class AggregatesViewSetTest(APITestCase):
    '''
    Test the interaction serializer and make sure the perms work and that the flagging system works.
    '''
    def setUp(self):
        self.today = date.today().isoformat()

        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')
        self.data_collector = User.objects.create_user(username='collector', password='testpass', role='data_collector')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        #set users orgs
        self.admin.organization = self.parent_org
        self.admin.save()
        self.manager.organization = self.parent_org
        self.manager.save()
        self.officer.organization = self.child_org
        self.officer.save()
        self.data_collector.organization = self.parent_org
        self.data_collector.save()

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)
        self.other_client_obj = Client.objects.create(name='Loser Client', created_by=self.admin)
        self.client_user.client_organization = self.client_obj
        self.client_user.save()

        #create two projects
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
        self.project.save()

        self.child_link = ProjectOrganization.objects.create(project=self.project, organization=self.child_org, parent_organization=self.parent_org)
        
        self.other_project = Project.objects.create(
            name='Beta Project',
            status=Project.Status.ACTIVE,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.other_project.organizations.set([self.other_org])

        #general respondent indicators
        self.indicator = Indicator.objects.create(code='1', name='First', indicator_type='respondent')
        self.indicator_2 = Indicator.objects.create(code='2', name='Second', indicator_type='respondent')

        #other special indicators
        self.event_ind = Indicator.objects.create(code='2', name='Second', indicator_type='event_no')
        self.event_org_ind = Indicator.objects.create(code='2', name='Second', indicator_type='event_org_no')
        self.social_ind = Indicator.objects.create(code='2', name='Second', indicator_type='social')

        #create some tasks
        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.task_2 = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator_2)
        self.social_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.social_ind)
        self.event_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.event_ind)
        self.event_org_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.event_org_ind)
        
        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.indicator)
        self.child_task_2 = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.indicator_2)
        self.child_social_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.social_ind)
        
        self.other_task =Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator)
        self.other_task_2 = Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator_2)
        self.other_social_task = Task.objects.create(project=self.other_project, organization=self.other_org, indicator=self.social_ind)
        self.other_project_task = Task.objects.create(project=self.other_project, organization=self.other_org, indicator=self.indicator)
        #create some respondents and some interactions for each
        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.MALE,
        )
        #mark as HIV positive
        HIVStatus.objects.create(respondent=self.respondent, hiv_positive=True, date_positive=date(2024, 1, 1))
        
        self.interaction_1_1 = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.task, 
        )
        self.interaction_1_2 = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.task_2, 
        )
        self.interaction_1_1_child = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.child_task, 
        )
        self.interaction_1_2_child = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.child_task_2, 
        )
        self.interaction_1_1_other = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.other_task, 
        )
        self.interaction_1_2_other = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.other_task_2, 
        )

        self.interaction_1_3_other = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.other_project_task, 
        )



        self.respondent2= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        #mark as pregnant
        Pregnancy.objects.create(respondent=self.respondent2, term_began=date(2024, 1, 1))

        self.interaction_2_1 = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.task, 
        )
        self.interaction_2_2 = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.task_2, 
        ) #should not count
        create_flag(self.interaction_2_2, 'test interaction', self.admin)

        self.interaction_2_1_child = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.child_task, 
        )
        self.interaction_2_2_child = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.child_task_2, 
        )
        self.interaction_2_1_other = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.other_task, 
        )
        self.interaction_2_2_other = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.other_task_2, 
        )

        self.respondent3= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        #create a flag on respondent 3
        create_flag(self.respondent3, "respondent", self.admin)
        self.interaction_3_1 = Interaction.objects.create(
            interaction_date=date(2024,6,1), 
            interaction_location='there', 
            respondent=self.respondent3, 
            task=self.task, 
        ) #should not count, respondent flag


        #create some events and counts
        self.event = Event.objects.create(
            name='Event',
            status=Event.EventStatus.COMPLETED,
            start='2024-07-09',
            end='2024-07-10',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task, self.task_2, self.event_org_task, self.event_task])
        self.event.organizations.set([self.parent_org, self.child_org])

        self.count1 = DemographicCount.objects.create(
            event=self.event,
            task= self.task,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_positive',
            count=10
        )
        self.count2 = DemographicCount.objects.create(
            event=self.event,
            task= self.task,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_negative',
            count=30
        )
        self.count3 = DemographicCount.objects.create(
            event=self.event,
            task= self.task,
            sex='F',
            citizenship='citizen',
            hiv_status='hiv_negative',
            count=78
        ) #should not count
        create_flag(self.count3, 'test', self.admin)

        self.count_task_2 = DemographicCount.objects.create(
            event=self.event,
            task= self.task_2,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_negative',
            count=36
        )

        self.event_count = Event.objects.create(
            name='Event',
            start='2024-07-09',
            status=Event.EventStatus.COMPLETED,
            end='2024-07-10',
            location='here',
            host=self.parent_org
        )
        self.event_count.tasks.set([self.event_org_task, self.event_task])
        self.event_count.organizations.set([self.child_org])

        self.event_planned = Event.objects.create(
            name='Event',
            start='2024-07-09',
            end='2024-07-10',
            location='here',
            host=self.parent_org,
            status=Event.EventStatus.PLANNED
        ) #should not count, planned
        self.event_planned.tasks.set([self.task, self.event_org_task, self.event_task])
        self.event_planned.organizations.set([self.parent_org])


        self.other_event = Event.objects.create(
            name='Event',
            start='2024-07-09',
            status=Event.EventStatus.COMPLETED,
            end='2024-07-10',
            location='here',
            host=self.other_org
        )
        self.other_event.organizations.set([self.other_org])
        self.other_event.tasks.set([self.other_task, self.other_project_task])

        self.count_other_proj = DemographicCount.objects.create(
            event=self.event,
            task= self.other_project_task,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_negative',
            count=17
        )


        #create some posts
        self.post = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=15,
            views=20,
            comments=4
        )
        self.post.tasks.set([self.social_task])

        self.post_flagged = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=15,
            views=20,
            comments=4
        ) #flagged, should not count
        self.post_flagged.tasks.set([self.social_task])
        create_flag(self.post_flagged, 'test post', self.admin)

        self.child_post = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=10,
            views=50,
            comments=17
        )
        self.child_post.tasks.set([self.child_social_task])
        
        self.other_post = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=6,
            views=43,
            comments=40
        )
        self.other_post.tasks.set([self.other_social_task])



    def test_get_indicator_admin(self):
        '''
        EXPECTED: 64
            7 FROM interactions (4r1 + 3r2) (2 should not count, ir flag and respondent flag)
            57 FROM events ((10+30 e1) + 17 e2) (78 from e1 should not count, count flag)
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.indicator.id}/')
        print('###===ADMIN===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 64)
    
    def test_get_indicator_client(self):
        '''
        EXPECTED: 46
            6 FROM interactions (3r1 + 3r2) (should not see interaction_2_2_other since this is with other_project)
            40 FROM events ((10+30 e1)) (should not see 37 from other event)
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.indicator.id}/')
        print('###===CLIENT===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 46)

    def test_get_indicator_me(self):
        '''
        EXPECTED: 44
            4 FROM interactions (2r1+2r2) (should not see 3 task_other/other_project_task intereactions)
            40 FROM events (10+30 e1) (should not see 37 from other event)
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.indicator.id}/')
        print('###===ME===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 44)
    
    def test_get_indicator_event(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.event_ind.id}/')
        print('###===ADMIN-EVENT===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts']['count'], 2)
    
    def test_get_indicator_event_org(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.event_org_ind.id}/')
        print('###===ADMIN-EVENT-ORG===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts']['count'], 3)
    
    def test_get_indicator_social_admin(self):
        '''
        EXPECT 
            -LIKES: 31, (15p + 10c + 6o) --> excl 15 flagged
            -VIEWS: 113 (20p, 50c, 43o) --> excl 20 flagged
            -COMMENTS: 61 (4p, 17c, 40o) --> excl 4 flagged
            -TOTAL: 205
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.social_ind.id}/')
        print('###===ADMIN-SOCIAL===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts']['total_engagement'], 205)
    

    def test_get_indicator_social_client(self):
        '''
        EXPECT 
            -LIKES: 25, (15p + 10c) --> excl 15 flagged + 6o
            -VIEWS: 70 (20p, 50c) --> excl 20 flagged + 430
            -COMMENTS: 21 (4p, 17c) --> excl 4 flagged +40o
            -TOTAL: 116
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.social_ind.id}/')
        print('###===ME-SOCIAL===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts']['total_engagement'], 116)

    def test_get_indicator_social_me(self):
        '''
        EXPECT 
            -LIKES: 25, (15p + 10c) --> excl 15 flagged + 6o
            -VIEWS: 70 (20p, 50c) --> excl 20 flagged + 430
            -COMMENTS: 21 (4p, 17c) --> excl 4 flagged +40o
            -TOTAL: 116
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(f'/api/analysis/counts/aggregate/{self.social_ind.id}/')
        print('###===ME-SOCIAL===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts']['total_engagement'], 116)
