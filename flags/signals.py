from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db.models import Q
from flags.models import Flag
from django.db import transaction
from messaging.models import Alert, AlertRecipient
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
User = get_user_model()

@receiver(post_save, sender=Flag)
def create_alert_on_flag(sender, instance, created, **kwargs):
    '''
    Flag alerts should be sent by default to:
        -admins
        -M&E officer of the organization of the flag
        -the user who caused the flag (if it was system generated)
    - instance (flag instnace): the flag object
    - created: was the object created. Do not alert for flag updates.
    '''

    if not created:
        return
    def send_alert():
        # Determine recipients
        q_caused_by = Q()
        if instance.caused_by:
            q_caused_by = Q(id=instance.caused_by.id)

        send_alert_to = User.objects.filter(
            q_caused_by |
            Q(role='meofficer', organization=instance.caused_by.organization if instance.caused_by else None) |
            Q(role='admin')
        ).distinct()

        # Create the alert
        alert = Alert.objects.create(
            subject='Flag Raised',
            body=f"{instance.get_reason_type_display()}: {instance.reason}",
            alert_type=Alert.AlertType.FLAG,
            content_type=instance.content_type,
            object_id=instance.object_id
        )

        # Create AlertRecipient objects
        AlertRecipient.objects.bulk_create([
            AlertRecipient(alert=alert, recipient=user) for user in send_alert_to
        ])
    transaction.on_commit(send_alert)

@receiver(pre_save, sender=Flag)
def create_alert_on_resolve(sender, instance, **kwargs):
    '''
    Let relevent users (same as above) know when a flag was resolved so they can review the reason.
    - instance (flag instnace): the flag object being resolved
    '''
    if not instance.pk:
        # New flag, nothing to compare
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    def send_alert():
        # Check if 'resolved' changed, and not auto_resolved
        if previous.resolved != instance.resolved and instance.resolved and not instance.auto_resolved:
            q_caused_by = Q()
            if instance.caused_by:
                q_caused_by = Q(id=instance.caused_by.id)

            send_alert_to = User.objects.filter(
                q_caused_by |
                Q(role='meofficer', organization=instance.caused_by.organization if instance.caused_by else None) |
                Q(role='admin')
            ).exclude(pk=instance.resolved_by.pk).distinct()

            alert = Alert.objects.create(
                subject='Flag Resolved',
                body = f"The following flag was resolved:\nReason: {instance.reason}\nResolution: {instance.resolved_reason}",
                alert_type=Alert.AlertType.FR, 
                content_type=instance.content_type,
                object_id=instance.object_id
            )

            AlertRecipient.objects.bulk_create([
                AlertRecipient(alert=alert, recipient=user) for user in send_alert_to
            ])

    transaction.on_commit(send_alert)