from django.test import TestCase
from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import Q

from projects.models import Project, Client, Task, ProjectOrganization, Target
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, InteractionSubcategory, KeyPopulation, KeyPopulationStatus
from events.models import Event, DemographicCount
from social.models import SocialMediaPost
from organizations.models import Organization
from events.models import Event
from indicators.models import Indicator, IndicatorSubcategory
from datetime import date, timedelta
from flags.utils import create_flag
User = get_user_model()

class AchievementTest(APITestCase):
    '''
    Test our target achievement (which also has the benefit of testing our org, project, start, and end filters) of
    our helper methods. 
    '''
    def setUp(self):
        self.today = date.today().isoformat()

        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        #set users orgs
        self.admin.organization = self.parent_org

        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)

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
        

        #general respondent indicators
        self.indicator = Indicator.objects.create(code='1', name='First', indicator_type='respondent')
        self.event_ind = Indicator.objects.create(code='2', name='Second', indicator_type='event_no')
        self.event_org_ind = Indicator.objects.create(code='2', name='Second', indicator_type='event_org_no')
        self.social_ind = Indicator.objects.create(code='2', name='Second', indicator_type='social')

        #create some tasks
        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.social_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.social_ind)
        self.event_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.event_ind)
        self.event_org_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.event_org_ind)
        
        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.indicator)
        self.child_social_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.social_ind)
        self.child_event_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.event_ind)
        self.child_event_org_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.event_org_ind)
        
        self.other_task =Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator)

        #create some respondents and some interactions for each
        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='BW',
            sex = Respondent.Sex.MALE,
        )
        
        self.interaction_1_1 = Interaction.objects.create(
            interaction_date=date(2025,1,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.task, 
        )
        self.interaction_1_1_child = Interaction.objects.create(
            interaction_date=date(2025,1,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.child_task, 
        )
        self.interaction_1_1_other = Interaction.objects.create(
            interaction_date=date(2025,1,1), 
            interaction_location='there', 
            respondent=self.respondent, 
            task=self.other_task, 
        ) #should not count unrelated org

        self.respondent2= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )

        self.interaction_2_1 = Interaction.objects.create(
            interaction_date=date(2025,1,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.task, 
        )
        self.interaction_2_2 = Interaction.objects.create(
            interaction_date=date(2025,1,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.child_task, 
        ) #should not count
        create_flag(self.interaction_2_2, 'test interaction', self.admin)

        self.interaction_2_1 = Interaction.objects.create(
            interaction_date=date(2025,6,1), 
            interaction_location='there', 
            respondent=self.respondent2, 
            task=self.task, 
        )#should not count, outside target range

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
            interaction_date=date(2025,1,1), 
            interaction_location='there', 
            respondent=self.respondent3, 
            task=self.task, 
        ) #should not count, respondent flag


        #create some events and counts
        self.event = Event.objects.create(
            name='Event',
            status=Event.EventStatus.COMPLETED,
            start='2025-01-09',
            end='2025-01-10',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.task])
        self.event.organizations.set([self.parent_org, self.child_org])

        self.count = DemographicCount.objects.create(
            event=self.event,
            task= self.task,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_positive',
            count=10
        )
        self.count_flag = DemographicCount.objects.create(
            event=self.event,
            task= self.task,
            sex='F',
            citizenship='citizen',
            hiv_status='hiv_negative',
            count=78
        ) #should not count
        create_flag(self.count_flag, 'test', self.admin)


        self.event_count = Event.objects.create(
            name='Event',
            start='2025-01-09',
            status=Event.EventStatus.COMPLETED,
            end='2025-01-10',
            location='here',
            host=self.parent_org
        )
        self.event_count.tasks.set([self.event_org_task, self.event_task])
        self.event_count.organizations.set([self.child_org, self.parent_org])

        self.child_event_count = Event.objects.create(
            name='Event',
            start='2025-01-09',
            status=Event.EventStatus.COMPLETED,
            end='2025-01-10',
            location='here',
            host=self.child_org
        )
        self.child_event_count.tasks.set([self.child_event_task])
        self.child_event_count.organizations.set([self.child_org])

        self.event_planned = Event.objects.create(
            name='Event',
            start='2025-01-09',
            end='2025-01-10',
            location='here',
            host=self.parent_org,
            status=Event.EventStatus.PLANNED
        ) #should not count, planned
        self.event_planned.tasks.set([self.task, self.event_org_task, self.event_task])
        self.event_planned.organizations.set([self.parent_org])


        self.other_event = Event.objects.create(
            name='Event',
            start='2025-01-09',
            status=Event.EventStatus.COMPLETED,
            end='2025-01-10',
            location='here',
            host=self.other_org
        ) #should not count, unrelated
        self.other_event.organizations.set([self.other_org])
        self.other_event.tasks.set([self.other_task])



        #create some posts
        self.post = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=15,
            views=20,
            comments=4,
            published_at='2025-01-01'
        )
        self.post.tasks.set([self.social_task])

        self.post_late = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=15,
            views=20,
            comments=4,
            published_at='2025-07-01'
        ) #should not count, outside target range
        self.post.tasks.set([self.social_task])


        self.post_flagged = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=15,
            views=20,
            comments=4,
            published_at='2025-01-01'
        ) #flagged, should not count
        self.post_flagged.tasks.set([self.social_task])
        create_flag(self.post_flagged, 'test post', self.admin)

        self.child_post = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.IG, 
            name='Test',
            likes=10,
            views=50,
            comments=17,
            published_at='2025-01-04'
        )
        self.child_post.tasks.set([self.child_social_task])
        
        self.other_post = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=6,
            views=43,
            comments=40,
            published_at='2025-01-01'
        ) #should not count, not asociated with task

        self.target = Target.objects.create(task=self.task, amount=60, start=date(2025,1,1), end=date(2025,3,30))
        self.event_no_target = Target.objects.create(task=self.event_task, amount =2, start=date(2025,1,1), end=date(2025,3,30))
        self.event_org_no_target = Target.objects.create(task=self.event_task, amount =2, start=date(2025,1,1), end=date(2025,3,30))
        self.social_target = Target.objects.create(task=self.social_task, amount=60, start=date(2025,1,1), end=date(2025,3,30))

    def test_respondent(self):
        '''
        EXPECTED: 13
            3 From interactions + 10 from count
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/targets/{self.target.id}/')
        print('###===ADMIN===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['achievement'], 13)
    def test_event_no(self):
        '''
        EXPECTED: 2 (1 parent + 1 child)
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/targets/{self.event_no_target.id}/')
        print('###===EVENT-NO===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['achievement'], 2)

    def test_event_org_no(self):
        '''
        EXPECTED: 2
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/targets/{self.event_org_no_target.id}/')
        print('###===EVENT-ORG-NO===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['achievement'], 2)
    def test_social(self):
        '''
        EXPECTED: 106
            L  V  C
            25+70+21 = 106 (measuring total enagement)
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/targets/{self.social_target.id}/')
        print('###===SOCIAL===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['achievement'], 116)
    