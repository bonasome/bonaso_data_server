from django.db import models

from django.conf import settings
from projects.models import Project
from respondents.models import Respondent
from events.models import Event

class FavoriteProject(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_projects')
    project = models.ForeignKey(Project, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'project')

class FavoriteEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_events')
    event = models.ForeignKey(Event, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'event')

class FavoriteRespondent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='favorite_respondents')
    respondent = models.ForeignKey(Respondent, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'respondent')