from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from projects.models import Project
from organizations.models import Organization
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

User = get_user_model()

class Alert(models.Model):
    class AlertType(models.TextChoices):
        SYS = 'system', _('System Message')
        FLAG = 'flag', _('Flag Alert')
        FR = 'flag_resolved', _('Flag Resolved')
        REM = 'reminder', _('Reminder')
    subject = models.CharField('Subject', max_length=255)
    body = models.TextField('Message Body')
    sent_on = models.DateTimeField(auto_now_add=True)
    alert_type = models.CharField(max_length=25, choices=AlertType.choices)
    recipients = models.ManyToManyField(User, through='AlertRecipient', related_name='alert_recipient')
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')

class AlertRecipient(models.Model):
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='recipient_links')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE)
    read = models.BooleanField(default=False)
    read_on = models.DateTimeField(null=True, blank=True)
    class Meta:
        unique_together = ('alert', 'recipient')

class Announcement(models.Model):
    subject = models.CharField('Subject', max_length=255)
    body = models.TextField('Message Body')
    sent_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcement_sender')
    sent_on = models.DateTimeField(auto_now_add=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True)
    cascade_to_children = models.BooleanField(default=False) #send to child orgs as well, if applicable

class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_sender')
    recipients = models.ManyToManyField(User, through='MessageRecipient', related_name='message_recipient')
    subject = models.CharField('Subject', max_length=255, null=True, blank=True) #null/blank for replies
    body = models.TextField('Message Body')
    sent_on = models.DateTimeField(auto_now_add=True)
    edited_on = models.DateTimeField(null=True, blank=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Response to')
    deleted_by_sender = models.BooleanField(default=False)
    send_to_admin = models.BooleanField(default=False)
    def __str__(self):
        return f'{self.subject} from {self.sender} on {self.sent_on.date()}'

class MessageRecipient(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='recipient_links')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE)
    read = models.BooleanField(default=False)
    read_on = models.DateTimeField(null=True, blank=True)
    actionable = models.BooleanField(default=False)
    completed = models.BooleanField(default=False)
    completed_on = models.DateTimeField(null=True, blank=True)
    deleted_by_recipient = models.BooleanField(default=False)

    class Meta:
        unique_together = ('message', 'recipient')
        indexes = [
            models.Index(fields=['recipient']),
            models.Index(fields=['read']),
            models.Index(fields=['actionable']),
            models.Index(fields=['completed']),
        ]
