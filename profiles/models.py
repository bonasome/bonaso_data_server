from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.conf import settings
from django.db import models

from django.contrib.auth import get_user_model
User = get_user_model()

class FavoriteObject(models.Model):
    '''
    Generic model that takes any supported object (see profiles.views --> favorite action) and allows a user to 
    favorite it. The front end uses this to collect these items on the home page.
    '''
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorites')

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey('content_type', 'object_id')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'content_type', 'object_id')
        indexes = [
            models.Index(fields=['user', 'content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.user} favorited {self.content_type} #{self.object_id}"