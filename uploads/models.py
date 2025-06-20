from django.db import models
from projects.models import Project
from organizations.models import Organization
from django.contrib.auth import get_user_model
User = get_user_model()

class NarrativeReport(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.SET_NULL, null=True, blank=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='file_uploaded_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    file = models.FileField(upload_to='narrative_reports/')
    title = models.CharField(max_length=255, verbose_name='Upload Title')
    description = models.TextField(verbose_name='Description of Upload', blank=True)
    
    def __str__(self):
        org_name = self.organization.name if self.organization else "Unknown Organization"
        proj_name = self.project.name if self.project else "Unknown Project"
        return f'Report from {org_name} for {proj_name} on {self.created_at.strftime("%Y-%m-%d")}'