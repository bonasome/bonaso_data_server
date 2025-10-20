from django.test import TestCase
from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db.models import Q

from projects.models import Project, Client, Task, ProjectOrganization
from respondents.models import Respondent, Interaction, Pregnancy, HIVStatus, KeyPopulation, KeyPopulationStatus, Response
from events.models import Event
from aggregates.models import AggregateCount, AggregateGroup
from social.models import SocialMediaPost
from organizations.models import Organization
from events.models import Event
from indicators.models import Indicator, Option, Assessment
from datetime import date, timedelta
from flags.utils import create_flag
User = get_user_model()

class AggregatesViewSetTest(APITestCase):
    '''
    Test our aggregtes viewset (and most of the helpers that aggregate our data). This viewset specifically
    doesn't support filters (those are more for charts), so those are tested elsewhere. This test also
    doesn't check project/org/start/end params since those are tested in test_achievement.

    I'm not gonna lie, this is a beheamoth network of tests and there's probably a few bugs and we definitely 
    didn't test everything, but hey, this is a start.
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
            published_at='2025-07-04'
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



    def test_get_indicator_admin(self):
        '''
        EXPECTED: 63
            6 FROM interactions (4r1 + 2r2) (2 should not count, ir flag and respondent flag)
            57 FROM events ((10+30 e1) + 17 e2) (78 from e1 should not count, count flag)
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/')
        print('###===ADMIN===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 63)
    
    def test_get_number_admin(self):
        '''
        EXPECTED: 66
            66 (22+22r1 + 22r2)
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator2.id}/')
        print('###===ADMIN-NUMBER===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 66)
    
    def test_get_misc_admin(self):
        '''
        EXPECTED: 66
            21 (10+11)
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.misc_ind.id}/')
        print('###===ADMIN-MISC===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 21)
    
    def test_get_indicator_client(self):
        '''
        EXPECTED: 46
            5 FROM interactions (3r1 + 2r2) (should not see interaction_2_2_other since this is with other_project)
            40 FROM events ((10+30 e1)) (should not see 37 from other group)
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/')
        print('###===CLIENT===###')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 45)

    def test_get_indicator_me(self):
        '''
        EXPECTED: 44
            3 FROM interactions (2r1+1r2) (should not see 3 task_other/other_project_task intereactions)
            40 FROM events (10+30 e1) (should not see 37 from other group)
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/')
        print('###===ME===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 43)
    
    def test_get_indicator_event_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_ind.id}/')
        print('###===ADMIN-EVENT===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 3)
    
    def test_get_indicator_event_client(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_ind.id}/')
        print('###===CLIENT-EVENT===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 2)
    
    def test_get_indicator_event_me(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_ind.id}/')
        print('###===ME-EVENT===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 2)
    
    def test_get_indicator_event_org_admin(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_org_ind.id}/')
        print('###===ADMIN-EVENT-ORG===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 4)
    
    def test_get_indicator_event_org_client(self):
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_org_ind.id}/')
        print('###===CLIENT-EVENT-ORG===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 3)
    
    def test_get_indicator_event_org_me(self):
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_org_ind.id}/')
        print('###===ME-EVENT-ORG===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 3)
    
    def test_get_indicator_social_admin(self):
        '''
        EXPECT 
            -LIKES: 31, (15p + 10c + 6o) --> excl 15 flagged
            -VIEWS: 113 (20p, 50c, 43o) --> excl 20 flagged
            -COMMENTS: 61 (4p, 17c, 40o) --> excl 4 flagged
            -TOTAL: 205
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.social_ind.id}/')
        print('###===ADMIN-SOCIAL===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 205)
    

    def test_get_indicator_social_client(self):
        '''
        EXPECT 
            -LIKES: 25, (15p + 10c) --> excl 15 flagged + 6o
            -VIEWS: 70 (20p, 50c) --> excl 20 flagged + 430
            -COMMENTS: 21 (4p, 17c) --> excl 4 flagged +40o
            -TOTAL: 116
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.social_ind.id}/')
        print('###===CLIENT-SOCIAL===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 116)

    def test_get_indicator_social_me(self):
        '''
        EXPECT 
            -LIKES: 25, (15p + 10c) --> excl 15 flagged + 6o
            -VIEWS: 70 (20p, 50c) --> excl 20 flagged + 430
            -COMMENTS: 21 (4p, 17c) --> excl 4 flagged +40o
            -TOTAL: 116
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.social_ind.id}/')
        print('###===ME-SOCIAL===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['counts'][0]['count'], 116)

    def test_respondent_split(self):
        '''
        EXPECT (Quarter) --7 total IR: 
            -Q1: 4ir + 40ev (44)
            -Q2: 2ir + 17ev (19)
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/?split=quarter')
        print('###===SPLIT-RESPONDENT-QUARTER===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        '''
        self.assertEqual(response.data['counts'][0]['period'], 'Q1 2025')
        self.assertEqual(response.data['counts'][0]['count'], 44)
        self.assertEqual(response.data['counts'][1]['period'], 'Q2 2025')
        self.assertEqual(response.data['counts'][1]['count'], 20)
        '''

    def test_respondent_repeat(self):
        '''
        EXPECT (Quarter) --7 total IR: 
            -Q1: 1
            -Q2: 1
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/?split=quarter&repeat_only=2')
        print('###===SPLIT-RESPONDENT-QUARTER-REPEAT===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_event_split(self):
        '''
        EXPECT (Quarter) -- 3 total: 
            -Q1: 1
            -Q2: 1
            -Q3: 1
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_ind.id}/?split=quarter')
        print('###===SPLIT-EVENT-QUARTER===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    
    def test_event_org_split(self):
        '''
        EXPECT (Quarter) --4 total: 
            -Q1: 2
            -Q2: 1
            -Q3: 1
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.event_org_ind.id}/?split=quarter')
        print('###===SPLIT-ORG-QUARTER===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        '''
        self.assertEqual(response.data['counts']['by_period']['Q1 2025'], 2)
        self.assertEqual(response.data['counts']['by_period']['Q2 2025'], 1)
        self.assertEqual(response.data['counts']['by_period']['Q3 2025'], 1)
        '''
    
    def test_social_split(self):
        '''
        EXPECT (Quarter) --3 total: 
                 L  V  C
            -Q1: 15 20 4 = 39
            -Q2: 6 43 40 = 89
            -Q3: 10 50 17 = 77
            
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.social_ind.id}/?split=quarter')
        print('###===SPLIT-SOCIAL-QUARTER===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_params_w_count(self):
        '''
        Make sure demographic breakdowns are in order. Theoretically you could get crazy with these permus, 
        but small test here. 
        C/POS: 14 (10(e) + 4 (ir))
        C/NEG: 30+17 (47 (e))
        NC/POS:
        NC/NEG: 2 (2 (ir))

        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/?citizenship=true&hiv_status=true')
        print('###===PARAMS-COUNT===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_params_no_count(self):
        '''
        If a count breakdown does not have a requested param, it should be ignored. 

        This will also test some of our multi-select/adjacent models
        TG/Preg: 2
        FSW/Preg: 2

        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/?pregnancy=true&kp_type=true')
        print('###===PARAMS-COUNT-SHOULD-NOT===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_params_option(self):
        '''
        EXPECT:
            -Option 1: 6
            -Option 2: 2
        '''
        self.client.force_authenticate(user=self.admin)
        
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.indicator.id}/?option=true')
        print('###===OPTION===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


    def test_social_platform_param(self):
        '''
        F
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/analysis/tables/aggregate/{self.social_ind.id}/?platform=true')
        print('###===SOCIAL-PLATFORM===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(f'/api/analysis/tables/aggregate/{self.social_ind.id}/?platform=true&split=month')
        print('###===SOCIAL-SPLIT-PLATFORM===###')
        print(response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        