from django.test import TestCase

from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from projects.models import Project, Client, Task, Target, ProjectOrganization
from organizations.models import Organization
from uploads.models import NarrativeReport
from datetime import date
User = get_user_model()


class UploadViewSetTest(APITestCase):
    def setUp(self):
        #set up users for each role
        self.admin = User.objects.create_user(username='admin', password='testpass', role='admin')
        self.officer = User.objects.create_user(username='meofficer', password='testpass', role='meofficer')
        self.data_collector = User.objects.create_user(username='data_collector', password='testpass', role='data_collector')

        #set up a parent/child org and an unrelated org
        self.parent_org = Organization.objects.create(name='Parent')
        self.child_org = Organization.objects.create(name='Child')
        self.other_org = Organization.objects.create(name='Other')
        
        self.admin.organization = self.parent_org
        self.officer.organization = self.parent_org
        self.data_collector.organization = self.parent_org

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
        self.project.organizations.set([self.parent_org, self.other_org, self.child_org])

        child_link = ProjectOrganization.objects.filter(organization=self.child_org).first()
        child_link.parent_organization = self.parent_org
        child_link.save()


        self.sample_file = SimpleUploadedFile("report.pdf", b"dummy content", content_type="application/pdf")
        self.child_report = NarrativeReport.objects.create(
            organization=self.child_org,
            project=self.project,
            uploaded_by=self.admin,
            file=self.sample_file,
            title="Monthly Report"
        )
        self.other_report = NarrativeReport.objects.create(
            organization=self.other_org,
            project=self.project,
            uploaded_by=self.admin,
            file=self.sample_file,
            title="Other Monthly Report"
        )

    def test_upload_valid_report(self):
        self.client.force_authenticate(user=self.officer)
        pdf_file = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4\n%Test PDF content", content_type="application/pdf"
        )

        response = self.client.post("/api/uploads/narrative-report/",
            {
                "organization": self.parent_org.id,
                "project": self.project.id,
                "file": pdf_file,
                "title": "Quarterly Report",
                "description": "Test upload"
            },
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(NarrativeReport.objects.filter(title="Quarterly Report").exists())

        report = NarrativeReport.objects.get(title="Quarterly Report")
        self.assertEqual(report.uploaded_by, self.officer)
    
        docx_file = SimpleUploadedFile(
            "test.docx", b"Test Word content", 
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        response = self.client.post("/api/uploads/narrative-report/",
            {
                "organization": self.parent_org.id,
                "project": self.project.id,
                "file": docx_file,
                "title": "Quarterly Report",
                "description": "Test upload"
            },
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        report = NarrativeReport.objects.filter(title="Quarterly Report").first()
        self.assertEqual(report.uploaded_by, self.officer)


    def test_upload_invalid_file(self):
        self.client.force_authenticate(user=self.officer)
        txt_file = SimpleUploadedFile(
            "bad.txt", b"This is a text file", content_type="text/plain"
        )

        response = self.client.post("/api/uploads/narrative-report/",
            {
                "organization": self.parent_org.id,
                "project": self.project.id,
                "file": txt_file,
                "title": "Quarterly Report",
                "description": "Test upload"
            },
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
    
    def test_no_perm(self):
        self.client.force_authenticate(user=self.data_collector)
        pdf_file = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4\n%Test PDF content", content_type="application/pdf"
        )

        response = self.client.post("/api/uploads/narrative-report/",
            {
                "organization": self.parent_org.id,
                "project": self.project.id,
                "file": pdf_file,
                "title": "Quarterly Report",
                "description": "Test upload"
            },
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    
    def test_child_org(self):
        self.client.force_authenticate(user=self.officer)
        pdf_file = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4\n%Test PDF content", content_type="application/pdf"
        )

        response = self.client.post("/api/uploads/narrative-report/",
            {
                "organization": self.child_org.id,
                "project": self.project.id,
                "file": pdf_file,
                "title": "Quarterly Report",
                "description": "Test upload"
            },
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_wrong_org(self):
        self.client.force_authenticate(user=self.officer)
        pdf_file = SimpleUploadedFile(
            "test.pdf", b"%PDF-1.4\n%Test PDF content", content_type="application/pdf"
        )

        response = self.client.post("/api/uploads/narrative-report/",
            {
                "organization": self.other_org.id,
                "project": self.project.id,
                "file": pdf_file,
                "title": "Quarterly Report",
                "description": "Test upload"
            },
            format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
    

    def test_admin_can_download_any_report(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/uploads/narrative-report/{self.other_report.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_officer_can_download_child_org_report(self):
        self.client.force_authenticate(user=self.officer)
        response = self.client.get(f'/api/uploads/narrative-report/{self.child_report.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_collector_cannot_download(self):
        self.client.force_authenticate(user=self.data_collector)
        response = self.client.get(f'/api/uploads/narrative-report/{self.other_report.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_officer_cannot_download_unrelated_org(self):
        self.client.force_authenticate(user=self.officer)
        response = self.client.get(f'/api/uploads/narrative-report/{self.other_report.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_missing_file(self):
        self.other_report.file = None
        self.other_report.save()

        self.client.force_authenticate(user=self.admin)
        response = self.client.get(f'/api/uploads/narrative-report/{self.report.id}/download/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)