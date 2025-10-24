from django.test import TestCase
from datetime import date
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model

from projects.models import Project, Client, Task, ProjectOrganization
from organizations.models import Organization
from indicators.models import Indicator
from social.models import SocialMediaPost
User = get_user_model()

class SocialPostViewSetTest(APITestCase):
    '''
    Testing the social media post viewset/serializer, creation, patching, and perms.
    '''
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.manager = User.objects.create_user(username='manager', password='testpass', role='manager')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.client_user = User.objects.create_user(username='client', password='testpass', role='client')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.manager.organization = self.parent_org
        self.officer.organization = self.child_org
        self.data_collector.organization = self.parent_org

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
        self.project.organizations.set([self.parent_org, self.child_org, self.other_org])

        child_link = ProjectOrganization.objects.filter(organization=self.child_org, project=self.project).first()
        child_link.parent_organization = self.parent_org
        child_link.save()

        self.client_user.client_organization = self.client_obj
        self.other_project = Project.objects.create(
            name='Beta Project',
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent_org, self.child_org])

        self.indicator = Indicator.objects.create(name='First', category=Indicator.Category.SOCIAL)
        self.indicator_2 = Indicator.objects.create(name='Second', category=Indicator.Category.SOCIAL)
        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.task_2 = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator_2)
        
        self.child_task = Task.objects.create(project=self.project, organization=self.child_org, indicator=self.indicator)
        self.other_task = Task.objects.create(project=self.project, organization=self.other_org, indicator=self.indicator)

        self.other_proj_not_child_task = Task.objects.create(project=self.other_project, organization=self.child_org, indicator=self.indicator)


        self.post = SocialMediaPost.objects.create(platform=SocialMediaPost.Platform.FB, name='Test', published_at=date(2025, 6, 7), organization=self.parent_org)
        self.post.tasks.set([self.task])

        self.other_post = SocialMediaPost.objects.create(platform=SocialMediaPost.Platform.FB, name='Test', organization=self.other_org)
        self.other_post.tasks.set([self.other_task])

        self.child_post = SocialMediaPost.objects.create(platform=SocialMediaPost.Platform.FB, name='Test', organization=self.child_org)
        self.child_post.tasks.set([self.child_task])

        self.child_post_other_proj = SocialMediaPost.objects.create(platform=SocialMediaPost.Platform.FB, name='Test', organization=self.child_org)
        self.child_post_other_proj.tasks.set([self.other_proj_not_child_task])



    def test_post_admin_view(self):
        '''
        Admins should be allowed to view all posts.
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/social/posts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 4)

    
    def test_post_non_admin(self):
        '''
        Non admins should only be allowed to see posts from their org/their child org
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/social/posts/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)

    def test_post_create(self):
        '''
        Posts should be created with the payload below.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'task_ids': [self.task.id, self.task_2.id],
            'organization_id': self.parent_org.id,
            'published_at': '2024-07-01',
            'platform': 'facebook',
            'name': 'King James',
        }
        response = self.client.post('/api/social/posts/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        post=SocialMediaPost.objects.filter(name='King James').first()
        self.assertEqual(post.created_by, self.admin)
        self.assertEqual(post.tasks.count(), 2)
    
    def test_create_child(self):
        '''
        Parent orgs can create for children (via assigned tasks)
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'task_ids': [self.child_task.id],
            'organization_id': self.child_org.id,
            'published_at': '2024-07-01',
            'platform': 'facebook',
            'name': 'King James',
        }
        response = self.client.post('/api/social/posts/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
    
    def test_create_wrong_org(self):
        '''
        Our code should be like NBA legend Dikembe Mutombo and block this from happening.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'task_ids': [self.other_task.id],
            'organization_id': self.other_org.id,
            'published_at': '2024-07-01',
            'platform': 'facebook',
            'name': 'King James',
        }
        response = self.client.post('/api/social/posts/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_wrong_proj_scope(self):
        '''
        If creating for child orgs, task assignment should be scoped by project.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'task_ids': [self.child_task.id, self.other_proj_not_child_task.id],
            'organization_id': self.child_org.id,
            'published_at': '2024-07-01',
            'platform': 'facebook',
            'name': 'King James',
        }
        response = self.client.post('/api/social/posts/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_create_org_task_mismatch(self):
        '''
        If creating for child orgs, task assignment should be scoped by project.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'task_ids': [self.child_task.id],
            'organization_id': self.parent_org.id,
            'published_at': '2024-07-01',
            'platform': 'facebook',
            'name': 'King James',
        }
        response = self.client.post('/api/social/posts/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_no_perm(self):
        '''
        Roles without permission should be blocked from doing stuff like this.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task_ids': [self.task.id],
            'organization_id': self.parent_org.id,
            'published_at': '2024-07-01',
            'platform': 'facebook',
            'name': 'King James',
        }
        response = self.client.post('/api/social/posts/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_metric_update(self):
        '''
        User can update metrics via an action
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'metrics': {
                'comments': 5,
                'views': 12
                
            }
        }
        response = self.client.patch(f'/api/social/posts/{self.post.id}/update-metrics/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        #perm dependent though
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'metrics': {
                'comments': 5,
                'views': 12
                
            }
        }
        response = self.client.patch(f'/api/social/posts/{self.child_post_other_proj.id}/update-metrics/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
