from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.contenttypes.fields import GenericRelation

from django.contrib.auth import get_user_model
User = get_user_model()
from projects.models import Task

class SocialMediaPost(models.Model):
    '''
    Post for recording social media data. Is linked to one or more tasks (if indicator is of the social type)
    and will contribute to targets.

    We collect platform information (where the post was made, with other option) as well as optionally a 
    link to the post. 
    '''
    class Platform(models.TextChoices):
        FB = 'facebook', _('Facebook')
        IG = 'instagram', _('Instagram')
        TT = 'tiktok', _('TikTok')
        TX = 'twitter', _('Twitter/X')
        YT = 'youtube', _('YouTube')
        OTHER = 'other', _('Another Platform')
    
    tasks = models.ManyToManyField(Task, through='SocialMediaPostTasks', blank=True)
    platform = models.CharField(max_length=50, choices=Platform.choices)
    other_platform = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    
    '''
    Likes, comments, views, reach, are sometimes called 'metrics.' It is important to note that if you add/
    remove metrics, you need to edit the metrics list on analysis/utils/aggregates --> social_aggregates
    and a similar list in social/serializers --> SocialMediaPostSerializer --> validate (both of these
    check the list of metrics to determine what fields to check/use for the function)
    '''
    likes = models.PositiveIntegerField(blank=True, null=True)
    views = models.PositiveIntegerField(blank=True, null=True)
    comments = models.PositiveIntegerField(blank=True, null=True)
    reach = models.PositiveIntegerField(blank=True, null=True)

    link_to_post = models.URLField(blank=True)
    published_at = models.DateField(blank=True, null=True)
    flags = GenericRelation('flags.Flag', related_query_name='flags')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='post_created_by')
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='post_updated_by')

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        super().clean()
        if self.platform == self.Platform.OTHER and not self.other_platform:
            raise ValidationError({'other_platform': 'Please specify the platform.'})

    def __str__(self):
        return f"Post: {self.name}"

class SocialMediaPostTasks(models.Model):
    '''
    Through table for social media post tasks.
    '''
    task = models.ForeignKey(Task, on_delete=models.PROTECT)
    post = models.ForeignKey(SocialMediaPost, on_delete=models.CASCADE)
