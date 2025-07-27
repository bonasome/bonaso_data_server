from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils.translation import gettext_lazy as _

from django.contrib.auth import get_user_model
User = get_user_model()

class Flag(models.Model):
    '''
    Generic flag model that is used to mark suspicious data for further review. Is attachable to any data
    model, but is mostly used for interactions, respondents, event counts, and social media posts.
    '''
    class FlagReason(models.TextChoices):
        DUP = 'duplicate', _('Potential Duplicate') #may be duplicated or needs review 
        ERR = 'entry_error', _('Data Entry Error') #likely typo (invalid Omang, etc.)
        SUS = 'suspicious', _('Suspicious Entry') #somethings off, like a count is higher than it should be
        IPR = 'inappropriate', _('Inappropriate Content') #(misc for wrong content type or bad information)
        MPRE = 'missing_prerequisite', _('Missing Prerequisite Information') #missing prerequisite content (i.e., interaction missing prerequisite)
        MD = 'missing_data', _('Missing Data') #some necessary information is missing
        OTHER = 'other', _('Other Reason')

    '''
    Track information about what was flagged and why.
    '''
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    target = GenericForeignKey("content_type", "object_id")

    reason_type = models.CharField(max_length=32, choices=FlagReason.choices, default='other')
    #NOTE: Reason is deliberately required for human made flags even if a flag_reason is selected to create a better audit trail.
    reason = models.TextField()
    auto_flagged = models.BooleanField(default=False) #system flagged it automatically
    caused_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='flag_caused_by') #if human created will default to created by, but for auto flags may be used to track the related user that triggered the action so it can be reviewed by a team

    '''
    Track information about when/why the flag was resolved.
    '''
    resolved = models.BooleanField(default=False)
    auto_resolved = models.BooleanField(default=False)
    resolved_reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='flag_updated_by') #for general updates
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='flag_created_by')

    resolved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='flag_resolved_by') #for resolution specifically
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Flag({self.get_reason_type_display()}) on {self.content_type} #{self.object_id}'
