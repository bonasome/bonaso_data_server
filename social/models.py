from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from users.models import User
from projects.models import Task

class SocialMediaPost(models.Model):
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
    likes = models.PositiveIntegerField(blank=True, null=True)
    views = models.PositiveIntegerField(blank=True, null=True)
    comments = models.PositiveIntegerField(blank=True, null=True)
    link_to_post = models.URLField(blank=True)
    published_at = models.DateField(blank=True, null=True)

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
    task = models.ForeignKey(Task, on_delete=models.PROTECT)
    post = models.ForeignKey(SocialMediaPost, on_delete=models.CASCADE)

class SocialMediaPostFlag(models.Model):
    social_media_post = models.ForeignKey("SocialMediaPost", on_delete=models.CASCADE, related_name="flags")
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='post_flag_created_by')
    resolved = models.BooleanField(default=False)
    resolved_reason = models.TextField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='post_flag_resolved_by')
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Flag  for social media post {self.social_media_post.name} for reason {self.reason}.'