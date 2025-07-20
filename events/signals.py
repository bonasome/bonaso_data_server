from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.db.models import Q
from events.models import Event, DemographicCount, CountFlag
from messaging.models import Alert, AlertRecipient
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
User = get_user_model()

@receiver(post_save, sender=CountFlag)
def create_alert_on_flag(sender, instance, created, **kwargs):
    if not created:
        return
    # Determine recipients
    send_alert_to = User.objects.filter(
        Q(role='meofficer', organization=instance.interaction.task.organization) |
        Q(role='admin')
    ).distinct()

    # Create the alert
    content_type = ContentType.objects.get_for_model(Event)
    alert = Alert.objects.create(
        subject='Flag Raised',
        body=instance.reason,
        alert_type=Alert.AlertType.FLAG,
        content_type=content_type,
        object_id=instance.count.event.id
    )

    # Create AlertRecipient objects
    AlertRecipient.objects.bulk_create([
        AlertRecipient(alert=alert, recipient=user) for user in send_alert_to
    ])

@receiver(pre_save, sender=CountFlag)
def create_alert_on_resolve(sender, instance, **kwargs):
    if not instance.pk:
        # New flag, nothing to compare
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return

    # Check if 'resolved' changed, and not auto_resolved
    if previous.resolved != instance.resolved and instance.resolved and not instance.auto_resolved:
        send_alert_to = User.objects.filter(role='admin').distinct()

        content_type = ContentType.objects.get_for_model(instance.count.event)
        alert = Alert.objects.create(
            subject='Flag Resolved',
            body=f"The following flag was resolved: {instance.reason}",
            alert_type=Alert.AlertType.FR, 
            content_type=content_type,
            object_id=instance.count.event.id
        )

        AlertRecipient.objects.bulk_create([
            AlertRecipient(alert=alert, recipient=user) for user in send_alert_to
        ])