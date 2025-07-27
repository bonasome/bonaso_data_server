from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
User = get_user_model()

from projects.models import Project, Client, ProjectOrganization, Task
from respondents.models import Respondent, Interaction
from indicators.models import Indicator
from organizations.models import Organization
from messaging.models import Alert, AlertRecipient
from datetime import date

class AlertViewSetTest(APITestCase):
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
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')
        self.other = User.objects.create_user(username='loser', password='testpass', role='manager')

        #set up a parent/child org and an unrelated org
        self.admin_org = Organization.objects.create(name='Admin')
        self.parent_org = Organization.objects.create(name='Parent')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.admin_org
        self.manager.organization = self.parent_org
        self.data_collector.organization = self.parent_org
        self.other.organization = self.other_org
        #set up a client
        self.client_obj = Client.objects.create(name='Test Client', created_by=self.admin)

        self.project = Project.objects.create(
            name='Alpha Project',
            client=self.client_obj,
            status=Project.Status.ACTIVE,
            start='2024-01-01',
            end='2024-12-31',
            description='Test project',
            created_by=self.admin,
        )
        self.project.organizations.set([self.parent_org])
        self.indicator = Indicator.objects.create(code='1', name='Parent')
        self.child_indicator = Indicator.objects.create(code='2', name='Child')
        self.child_indicator.prerequisites.set([self.indicator])
        
        self.task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.indicator)
        self.prereq_task = Task.objects.create(project=self.project, organization=self.parent_org, indicator=self.child_indicator)

        self.respondent= Respondent.objects.create(
            is_anonymous=True,
            age_range=Respondent.AgeRanges.T_24,
            village='Testingplace',
            district= Respondent.District.CENTRAL,
            citizenship='test',
            sex = Respondent.Sex.FEMALE,
        )
    
    def test_auto_flag_alert(self):
        '''
        Not working, signals aren't firing.
        '''
        self.client.force_authenticate(user=self.data_collector)
        valid_payload = {
            'task': self.prereq_task.id,
            'interaction_date': '2024-06-15',
            'interaction_location': 'That place that sells chili.',
            'respondent': self.respondent.id,
        }
        response = self.client.post('/api/record/interactions/', valid_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ir = Interaction.objects.filter(task=self.prereq_task, respondent=self.respondent).first()
        self.assertEqual(ir.flags.count(), 1)

        alerts = Alert.objects.all()
        self.assertEqual(alerts.count(), 1)
        alert_rec = AlertRecipient.objects.all()
        self.assertEqual(alert_rec.count(), 3)


        
    
