from io import BytesIO
from openpyxl import Workbook
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from organizations.models import Organization
from projects.models import Project, Task, Client
from indicators.models import Indicator
User = get_user_model()

class TemplateUploadTests(APITestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Parent Org')
        self.child_org = Organization.objects.create(name='Child Org', parent_organization=self.org)

        self.client_obj = Client.objects.create(name='Test Client')
        self.project = Project.objects.create(
            name='Beta Project',
            client=self.client_obj,
            status=Project.Status.PLANNED,
            start='2024-02-01',
            end='2024-10-31',
            description='Second project',
        )
        self.project.organizations.set([self.org])

        self.ind = Indicator.objects.create(code='1', name='Test Ind')
        self.ind2 = Indicator.objects.create(code='2', name='Test Ind 2')

        self.project.indicators.set([self.ind, self.ind2])

        self.task = Task.objects.create(project=self.project, organization=self.org, indicator=self.ind)
        self.task2 = Task.objects.create(project=self.project, organization=self.org, indicator=self.ind2)

        self.user = User.objects.create_user(username='manager', password='pass', role='manager', organization=self.org)
        self.client.force_authenticate(user=self.user)

        self.url = reverse('interaction-post-template')  # Use your actual route name

    def create_workbook(self, b1=None, b2=None, include_metadata=True, include_data=True):
        wb = Workbook()
        if include_metadata:
            ws = wb.active
            ws.title = 'Metadata'
            ws['B1'] = b1
            ws['B2'] = b2
        if include_data:
            wb.create_sheet(title='Data')
        return wb

    def test_no_file_uploaded(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('No file was uploaded', str(response.data))

    def test_invalid_file_type(self):
        dummy_file = BytesIO(b"not excel")
        dummy_file.name = 'data.csv'
        response = self.client.post(self.url, {'file': dummy_file}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('must be an .xlsx', str(response.data))

    def test_missing_metadata_sheet(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "NotMetadata"
        file_obj = BytesIO()
        wb.save(file_obj)
        file_obj.name = 'test.xlsx'
        file_obj.seek(0)

        response = self.client.post(self.url, {'file': file_obj}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Unable to read 'Metadata'", str(response.data))

    def test_non_numeric_ids(self):
        wb = self.create_workbook('abc', 'xyz')
        file_obj = BytesIO()
        wb.save(file_obj)
        file_obj.name = 'test.xlsx'
        file_obj.seek(0)

        response = self.client.post(self.url, {'file': file_obj}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('must be numeric', str(response.data))

    def test_permission_denied_to_other_org(self):
        wb = self.create_workbook(1, 999)  # 999 is not valid org for this user
        file_obj = BytesIO()
        wb.save(file_obj)
        file_obj.name = 'test.xlsx'
        file_obj.seek(0)

        response = self.client.post(self.url, {'file': file_obj}, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_successful_upload(self):
        wb = self.create_workbook(self.project.id, self.org.id)
        file_obj = BytesIO()
        wb.save(file_obj)
        file_obj.name = 'test.xlsx'
        file_obj.seek(0)

        response = self.client.post(self.url, {'file': file_obj}, format='multipart')
        self.assertNotIn(response.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN])
        print("Status Code:", response.status_code)
        print("Response Data:", response.data)