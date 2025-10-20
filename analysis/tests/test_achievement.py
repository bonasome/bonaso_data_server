from django.test import TestCase
from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import Q

from projects.models import Project, Client, Task, ProjectOrganization, Target
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, Response, KeyPopulation, KeyPopulationStatus
from events.models import Event
from social.models import SocialMediaPost
from organizations.models import Organization
from events.models import Event
from aggregates.models import AggregateCount, AggregateGroup
from indicators.models import Indicator, Option, Assessment
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
            start='2025-02-01',
            end='2025-10-31',
            description='Second project',
            created_by=self.admin,
        )
        self.other_project.organizations.set([self.other_org])

        #simple assessment
        self.assessment = Assessment.objects.create(name='Ass')
        #general respondent indicators
        self.indicator = Indicator.objects.create(assessment=self.assessment, name='Select the Option', type=Indicator.Type.MULTI, allow_aggregate=True)
        self.option1 = Option.objects.create(name='Option 1', indicator=self.indicator)
        self.option2 = Option.objects.create(name='Option 2', indicator=self.indicator)
        self.indicator2 = Indicator.objects.create(assessment=self.assessment, name='Enter the Number', type=Indicator.Type.INT)

        #other special indicators
        self.event_ind = Indicator.objects.create(name='Number of Events Held', category=Indicator.Category.EVENTS)
        self.event_org_ind = Indicator.objects.create(name='Number of Orgs Trained', category=Indicator.Category.ORGS)
        self.social_ind = Indicator.objects.create(name='Social Media', category=Indicator.Category.SOCIAL)
        self.misc_ind = Indicator.objects.create(name='Whatever', category=Indicator.Category.MISC)

        #create some tasks
        self.task = Task.objects.create(project=self.project, organization=self.parent_org, assessment=self.assessment)
        self.social_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.social_ind)
        self.event_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.event_ind)
        self.event_org_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.event_org_ind)
        self.child_event_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.event_ind)
        self.misc_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.misc_ind)

        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, assessment=self.assessment)
        self.child_social_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.social_ind)
        
        self.other_task =Task.objects.create(project=self.project, organization=self.other_org, assessment=self.assessment)
        self.other_social_task = Task.objects.create(project=self.other_project, organization=self.other_org, indicator=self.social_ind)

        self.other_project_task = Task.objects.create(project=self.other_project, organization=self.other_org, assessment=self.assessment)
        
        self.other_event_task = Task.objects.create(project=self.other_project, organization=self.other_org, indicator=self.event_ind)
        self.other_event_org_task = Task.objects.create(project=self.other_project, organization=self.other_org, indicator=self.event_org_ind)
        
        #create some respondents and some interactions for each
        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='BW',
            sex = Respondent.Sex.MALE,
        )
        #mark as HIV positive
        HIVStatus.objects.create(respondent=self.respondent, hiv_positive=True, date_positive=date(2025, 1, 1))
        
        self.interaction1 = Interaction.objects.create(interaction_date='2025-01-01', interaction_location='There', task=self.task, respondent=self.respondent)
        self.response1_1 = Response.objects.create(indicator=self.indicator, interaction=self.interaction1, response_option=self.option1, response_date='2025-01-01', response_location='There')
        self.response1_1_1 = Response.objects.create(indicator=self.indicator, interaction=self.interaction1, response_option=self.option2, response_date='2025-01-01', response_location='There')
        self.response1_2 = Response.objects.create(indicator=self.indicator2, interaction=self.interaction1, response_value='22', response_date='2025-01-01', response_location='There')
        
        self.interaction1_child = Interaction.objects.create(interaction_date='2025-01-01', interaction_location='There', task=self.child_task, respondent=self.respondent)
        self.response1_child = Response.objects.create(indicator=self.indicator, interaction=self.interaction1_child, response_option=self.option1, response_date='2025-01-01', response_location='There')
        self.response1_child2 = Response.objects.create(indicator=self.indicator2, interaction=self.interaction1_child, response_value='22', response_date='2025-01-01', response_location='There')
        
        self.interaction1_other = Interaction.objects.create(interaction_date='2025-01-01', interaction_location='There', task=self.other_task, respondent=self.respondent)
        self.response1_other = Response.objects.create(indicator=self.indicator, interaction=self.interaction1_other, response_option=self.option1, response_date='2025-01-01', response_location='There')

        self.interaction1_other_project = Interaction.objects.create(interaction_date='2025-01-01', interaction_location='There', task=self.other_project_task, respondent=self.respondent)
        self.response1_other_proj = Response.objects.create(indicator=self.indicator, interaction=self.interaction1_other_project, response_option=self.option1, response_date='2025-01-01', response_location='There')

        self.respondent2= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        #mark as pregnant
        Pregnancy.objects.create(respondent=self.respondent2, term_began=date(2025, 1, 1))
        fsw = KeyPopulation.objects.create(name=KeyPopulation.KeyPopulations.FSW)
        tg = KeyPopulation.objects.create(name=KeyPopulation.KeyPopulations.TG)
        tgr2 = KeyPopulationStatus.objects.create(key_population=tg, respondent=self.respondent2)
        fswr2 = KeyPopulationStatus.objects.create(key_population=fsw, respondent=self.respondent2)
        self.respondent2.kp_status.set([fswr2.id, tgr2.id])
        self.respondent2.save()

        self.interaction2 = Interaction.objects.create(interaction_date='2025-06-01', interaction_location='There', task=self.task, respondent=self.respondent2)
        self.response2_1 = Response.objects.create(indicator=self.indicator, interaction=self.interaction2, response_option=self.option1, response_date='2025-05-01', response_location='There')
        self.response2_1_1 = Response.objects.create(indicator=self.indicator, interaction=self.interaction2, response_option=self.option2, response_date='2025-05-01', response_location='There')
        self.response2_2 = Response.objects.create(indicator=self.indicator2, interaction=self.interaction2, response_value='22', response_date='2025-05-01', response_location='There')
        
        self.interaction2_child = Interaction.objects.create(interaction_date='2025-06-01', interaction_location='There', task=self.child_task, respondent=self.respondent2)
        self.response2_child = Response.objects.create(indicator=self.indicator, interaction=self.interaction2_child, response_option=self.option1, response_date='2025-05-01', response_location='There')
        self.response2_child2 = Response.objects.create(indicator=self.indicator2, interaction=self.interaction2_child, response_value='22', response_date='2025-05-01', response_location='There')
        create_flag(self.interaction2_child, 'test interaction', self.admin)

        self.interaction2_other = Interaction.objects.create(interaction_date='2025-06-01', interaction_location='There', task=self.other_task, respondent=self.respondent2)
        self.response2_other = Response.objects.create(indicator=self.indicator, interaction=self.interaction2_other, response_option=self.option1, response_date='2025-05-01', response_location='There')

        self.respondent3= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
        #create a flag on respondent 3
        create_flag(self.respondent3, "test respondent", self.admin)
        self.interaction3 = Interaction.objects.create(interaction_date='2025-05-01', interaction_location='There', task=self.task, respondent=self.respondent3)
        self.response3_1 = Response.objects.create(indicator=self.indicator, interaction=self.interaction3, response_option=self.option1, response_date='2025-05-01', response_location='There')
        self.response3_1_1 = Response.objects.create(indicator=self.indicator, interaction=self.interaction3, response_option=self.option2, response_date='2025-05-01', response_location='There')
        self.response3_2 = Response.objects.create(indicator=self.indicator2, interaction=self.interaction3, response_value='22', response_date='2025-05-01', response_location='There')
        
        self.aggie_group1 = AggregateGroup.objects.create(
            start='2025-01-09', 
            end='2025-01-10', 
            project=self.project, 
            organization=self.parent_org, 
            indicator=self.indicator
        )
        self.count1 = AggregateCount.objects.create(
            group=self.aggie_group1,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_positive',
            value=10
        )
        self.count1_2 = AggregateCount.objects.create(
            group=self.aggie_group1,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_negative',
            value=30
        )
        
        self.count3 = AggregateCount.objects.create(
            group=self.aggie_group1,
            sex='F',
            citizenship='citizen',
            hiv_status='hiv_negative',
            value=78
        ) #should not count
        create_flag(self.count3, 'test', self.admin)

        self.aggie_group_misc = AggregateGroup.objects.create(
            start='2025-01-09', 
            end='2025-01-10', 
            project=self.project, 
            organization=self.parent_org, 
            indicator=self.misc_ind
        )
        self.count_misc = AggregateCount.objects.create(
            group=self.aggie_group_misc,
            sex='M',
            citizenship='citizen',
            value=10
        )
        self.count_misc2 = AggregateCount.objects.create(
            group=self.aggie_group_misc,
            sex='F',
            citizenship='citizen',
            value=11
        )

        self.aggie_group_other_proj = AggregateGroup.objects.create(
            start='2025-06-09', 
            end='2025-06-10', 
            project=self.other_project, 
            organization=self.other_org, 
            indicator=self.indicator
        )
        self.count_other_proj = AggregateCount.objects.create(
            group=self.aggie_group_other_proj,
            sex='M',
            citizenship='citizen',
            hiv_status='hiv_negative',
            value=17
        )

        #create some events and counts
        self.event = Event.objects.create(
            name='Event',
            status=Event.EventStatus.COMPLETED,
            start='2025-01-09',
            end='2025-01-10',
            location='here',
            host=self.parent_org
        )
        self.event.tasks.set([self.event_org_task, self.event_task])
        self.event.organizations.set([self.parent_org, self.child_org])

        self.event_count = Event.objects.create(
            name='Event',
            start='2025-07-09',
            status=Event.EventStatus.COMPLETED,
            end='2025-07-10',
            location='here',
            host=self.parent_org
        )
        self.event_count.tasks.set([self.event_org_task, self.event_task])
        self.event_count.organizations.set([self.child_org])

        #create some events and counts
        self.event_child = Event.objects.create(
            name='Event',
            status=Event.EventStatus.COMPLETED,
            start='2025-01-09',
            end='2025-01-10',
            location='here',
            host=self.child_org
        )
        self.event_child.tasks.set([self.child_event_task])

        self.event_planned = Event.objects.create(
            name='Event',
            start='2025-11-09',
            end='2025-11-10',
            location='here',
            host=self.parent_org,
            status=Event.EventStatus.PLANNED
        ) #should not count, planned
        self.event_planned.tasks.set([self.event_org_task, self.event_task])
        self.event_planned.organizations.set([self.parent_org])


        self.other_event = Event.objects.create(
            name='Event',
            start='2025-05-09',
            status=Event.EventStatus.COMPLETED,
            end='2025-05-10',
            location='here',
            host=self.other_org
        )
        self.other_event.organizations.set([self.other_org])
        self.other_event.tasks.set([self.other_event_org_task, self.other_event_task])


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

        self.post_flagged = SocialMediaPost.objects.create(
            platform=SocialMediaPost.Platform.FB, 
            name='Test',
            likes=15,
            views=20,
            comments=4,
            published_at='2025-06-01'
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
            published_at='2025-06-01'
        )
        self.other_post.tasks.set([self.other_social_task])

        self.target = Target.objects.create(indicator=self.indicator, organization=self.parent_org, project=self.project, amount=60, start=date(2025,1,1), end=date(2025,3,30))
        self.event_no_target = Target.objects.create(indicator=self.event_ind, organization=self.parent_org, project=self.project, amount =2, start=date(2025,1,1), end=date(2025,3,30))
        self.event_org_no_target = Target.objects.create(indicator=self.event_org_ind, organization=self.parent_org, project=self.project, amount =2, start=date(2025,1,1), end=date(2025,3,30))
        self.social_target = Target.objects.create(indicator=self.social_ind, organization=self.parent_org, project=self.project, amount=60, start=date(2025,1,1), end=date(2025,3,30))

    def test_respondent(self):
        '''
        EXPECTED: 13
            2 From interactions + 40 from count
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/manage/targets/{self.target.id}/')
        print('###===ADMIN===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['achievement'], 42)
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
    