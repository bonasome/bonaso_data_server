from django.db import models

from django.conf import settings
from projects.models import Project, Task
from respondents.models import Respondent

class FavoriteProject(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_projects')
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'project')

class FavoriteTask(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_tasks')
    task = models.ForeignKey(Task, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'task')

class FavoriteRespondent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_respondents')
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'respondent')