from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from projects.models import Project
from organizations.models import Organization

from django.contrib.auth import get_user_model
User = get_user_model()

class Alert(models.Model):
    '''
    An alert is a system generated message that only has recipients and read status. Mostly designed to alert users
    to flags, but also reminds them of potential project deadlines.
    '''
    class AlertType(models.TextChoices):
        SYS = 'system', _('System Message') #generic
        FLAG = 'flag', _('Flag Alert') #alerts on a flag (for review)
        FR = 'flag_resolved', _('Flag Resolved') #alerts when a flag is resolved (for review)
        REM = 'reminder', _('Reminder') #mostly for deadlines, but may be expanded in the future

    subject = models.CharField('Subject', max_length=255)
    body = models.TextField('Message Body')
    alert_type = models.CharField(max_length=25, choices=AlertType.choices)
    recipients = models.ManyToManyField(User, through='AlertRecipient', related_name='alert_recipient')
    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True) #used in the event we may want to provide a link for the frontend to a specific object
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey('content_type', 'object_id')
    sent_on = models.DateTimeField(auto_now_add=True)
    
class AlertRecipient(models.Model):
    '''
    Through model that also tracks read status.
    '''
    alert = models.ForeignKey(Alert, on_delete=models.CASCADE, related_name='recipient_links')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE)
    read = models.BooleanField(default=False)
    read_on = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('alert', 'recipient')

class Announcement(models.Model):
    '''
    Primarily a vehicle for admins to announce site updates, but can double as a tool for admins/higher roles
    to set announcements for projects (deadlines, important dates, etc.)
    '''
    subject = models.CharField('Subject', max_length=255)
    body = models.TextField('Message Body')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True) #link only to members of a specific project
    organizations = models.ManyToManyField(Organization, through='AnnouncementOrganization', blank=True)
    cascade_to_children = models.BooleanField(default=False) #send to child orgs as well, if applicable
    visible_to_all = models.BooleanField(default=False) #is publid

    sent_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcement_sender', null=True, blank=True)
    sent_on = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='announcement_updater', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

class AnnouncementOrganization(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)

class AnnouncementRecipient(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True)

class Message(models.Model):
    '''
    Communication between two or more users in a thread style system. Includes subject/body.
    Recipients cannot be edited, but text can.

    Parent messages are used to track replies, null is assumed to be a new thread.
    '''
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='message_sender', null=True, blank=True)
    recipients = models.ManyToManyField(User, through='MessageRecipient', related_name='message_recipient')
    subject = models.CharField('Subject', max_length=255, null=True, blank=True) #null/blank for replies
    body = models.TextField('Message Body')
    send_to_admin = models.BooleanField(default=False)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, verbose_name='Response to')

    sent_on = models.DateTimeField(auto_now_add=True)
    edited_on = models.DateTimeField(null=True, blank=True)
    deleted_by_sender = models.BooleanField(default=False)
    
    def __str__(self):
        return f'{self.subject} from {self.sender} on {self.sent_on.date()}'

class MessageRecipient(models.Model):
    '''
    Through model for tracking message recipients, but also allows to track specific read/action statuses.

    Messages can be assigned as tasks to individual users and marked complete individually as well.
    '''
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
