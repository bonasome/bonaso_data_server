from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
User = get_user_model()

from projects.models import Project, Client, ProjectOrganization, ProjectActivity, ProjectDeadline, ProjectDeadlineOrganization
from organizations.models import Organization
from datetime import date


class ProjectRelatedViewSetTest(APITestCase):
    '''
    This is a general test for project adjacent things (activities, deadlines) since they mostly 
    share the same logic/permission classes.

    We're not testing these as rigorously yet since these are nice to have and not critical to the data 
    collection.Just make sure the basics work.
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

        self.planned_project = Project.objects.create(
            name='Beta Project',
            client=self.other_client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
            created_by=self.admin,
        )

        self.activity_parent = ProjectActivity.objects.create(
            project=self.project,
            visible_to_all=False,
            cascade_to_children=False,
            name='Test Parent',
            start = date(2024,1,12),
            end = date(2024,1,12),
            status = Project.Status.ACTIVE,
            category = ProjectActivity.Category.GEN,
            created_by=self.admin,
        )
        self.activity_parent.organizations.set([self.parent_org, self.other_org])
        
        self.activity_child = ProjectActivity.objects.create(
            project=self.project,
            visible_to_all=False,
            cascade_to_children=False,
            name='Test Active',
            start = date(2024,1,12),
            end = date(2024,1,12),
            status = Project.Status.ACTIVE,
            category = ProjectActivity.Category.GEN,
            created_by=self.admin,
        )
        self.activity_child.organizations.set([self.child_org])

        self.activity_other = ProjectActivity.objects.create(
            project=self.project,
            visible_to_all=False,
            cascade_to_children=False,
            name='Test Child',
            start = date(2024,1,12),
            end = date(2024,1,12),
            status = Project.Status.ACTIVE,
            category = ProjectActivity.Category.GEN,
            created_by=self.admin,
        )
        self.activity_other.organizations.set([self.other_org])

        self.activity_planned = ProjectActivity.objects.create(
            project=self.planned_project,
            visible_to_all=True,
            cascade_to_children=False,
            name='Test Planned',
            start = date(2024,1,12),
            end = date(2024,1,12),
            status = Project.Status.PLANNED,
            category = ProjectActivity.Category.GEN,
            created_by=self.admin,
        )
        self.activity_parent.organizations.set([self.parent_org, self.other_org])
        
        self.deadline = ProjectDeadline.objects.create(
            project=self.project,
            visible_to_all=True,
            cascade_to_children=False,
            name='Test Child',
            deadline_date = date(2024,1,12),
            created_by=self.admin,
        )
    def test_activity_admin_view(self):
        '''
        Admins can view all related activities
        '''
        self.client.force_authenticate(user=self.admin)
        response = self.client.get('/api/manage/activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 4)
    
    def test_activity_parent_view(self):
        '''
        Non admins can only see public (visible to all) or activities scoped to them
        '''
        self.client.force_authenticate(user=self.manager)
        response = self.client.get('/api/manage/activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_activity_child_view(self):
        '''
        Child orgs can't see parents stuff unless explicity assigned/cascaded
        '''
        self.client.force_authenticate(user=self.officer)
        response = self.client.get('/api/manage/activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_target_client_view(self):
        '''
        Clients can see activities for projects they own
        '''
        self.client.force_authenticate(user=self.client_user)
        response = self.client.get('/api/manage/activities/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)
    
    def test_activity_create_parent(self):
        '''
        Higher roles can create activities for their org and their children.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'project_id': self.project.id,
            'start': '2024-07-01',
            'end': '2024-07-01',
            'status': 'Planned',
            'category': 'training',
            'name': 'bro',
            'cascade_to_children': True,
        }
        response = self.client.post('/api/manage/activities/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = ProjectActivity.objects.filter(name='bro').first()
        self.assertEqual(created.organizations.count(), 2)
    
    def test_activity_patch(self):
        '''
        Can also patch activities.
        '''
        self.client.force_authenticate(user=self.admin)
        valid_payload = {
            'organization_ids': [self.parent_org.id, self.child_org.id],
            'start': '2024-02-01',
            'end': '2024-02-03'
        }
        response = self.client.patch(f'/api/manage/activities/{self.activity_parent.id}/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        created = ProjectActivity.objects.filter(name='Test Parent').first()
        self.assertEqual(created.organizations.count(), 2)
        self.assertEqual(created.created_by, self.admin)

    def test_deadline_create_parent(self):
        '''
        Parents can also create deadlines.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'project_id': self.project.id,
            'deadline_date': '2024-07-01',
            'name': 'bro',
            'cascade_to_children': True,
        }
        response = self.client.post('/api/manage/deadlines/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = ProjectDeadline.objects.filter(name='bro').first()
        self.assertEqual(created.organizations.count(), 2)
        self.assertEqual(created.created_by, self.manager)
    
    def test_deadline_resolve(self):
        '''
        Test resolving deadlines action.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'organization_id': self.parent_org.id,
        }
        response = self.client.patch(f'/api/manage/deadlines/{self.deadline.id}/mark-complete/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        dl_link = ProjectDeadlineOrganization.objects.filter(deadline=self.deadline, organization=self.parent_org).first()
        self.assertEqual(dl_link.completed, True)
        self.assertEqual(dl_link.updated_by, self.manager)


    def test_bad_org(self):
        '''
        Non admins cannot create events for unrelated orgs.
        '''
        self.client.force_authenticate(user=self.manager)
        valid_payload = {
            'project_id': self.project.id,
            'start': '2024-07-01',
            'end': '2024-07-01',
            'status': 'Planned',
            'category': 'training',
            'name': 'bro',
            'cascade_to_children': False,
            'organization_ids': [self.other_org.id]
        }
        response = self.client.post('/api/manage/activities/', valid_payload, format='json')
        print(response.json())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)