from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db.models import Q
from respondents.models import KeyPopulationStatus, DisabilityStatus, HIVStatus, RespondentAttribute, RespondentAttributeType, InteractionFlag, Interaction
from django.db import transaction
from messaging.models import Alert, AlertRecipient
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
User = get_user_model()
def update_attribute(respondent, attribute_enum, should_add):
    try:
        attr_type, _ = RespondentAttributeType.objects.get_or_create(name=attribute_enum)
        print(attr_type)
        if should_add:
            RespondentAttribute.objects.update_or_create(
                respondent=respondent,
                attribute=attr_type,
                defaults={'auto_assigned': True}
            )
        else:
            RespondentAttribute.objects.filter(
                respondent=respondent,
                attribute=attr_type,
                auto_assigned=True
            ).delete()
    except RespondentAttributeType.DoesNotExist:
        print('WARNING: An attribute was submitted that was not found in the database.')
        pass  # You may want to log this

# === Key Population ===
@receiver(post_save, sender=KeyPopulationStatus)
@receiver(post_delete, sender=KeyPopulationStatus)
def sync_kp_attribute(sender, instance, **kwargs):
    respondent = instance.respondent
    def after_commit():
        should_add = KeyPopulationStatus.objects.filter(respondent=respondent).exists()
        update_attribute(respondent, RespondentAttributeType.Attributes.KP, should_add)

    transaction.on_commit(after_commit)

# === Disability ===
@receiver(post_save, sender=DisabilityStatus)
@receiver(post_delete, sender=DisabilityStatus)
def sync_disability_attribute(sender, instance, **kwargs):
    respondent = instance.respondent
    def after_commit():
        should_add = DisabilityStatus.objects.filter(respondent=respondent).exists()
        update_attribute(respondent, RespondentAttributeType.Attributes.PWD, should_add)
    transaction.on_commit(after_commit)
# === HIV Status ===
@receiver(post_save, sender=HIVStatus)
@receiver(post_delete, sender=HIVStatus)
def sync_hiv_attribute(sender, instance, **kwargs):
    respondent = instance.respondent
    def after_commit():
        should_add = HIVStatus.objects.filter(respondent=respondent, hiv_positive=True).exists()
        update_attribute(respondent, RespondentAttributeType.Attributes.PLWHIV, should_add)
    transaction.on_commit(after_commit)

@receiver(post_save, sender=Interaction)
def handle_govern_interaction(sender, instance, created, **kwargs):
    if not created:
        return  # Only run on creation

    task = instance.task
    respondent = instance.respondent

    if not task or not respondent:
        return

    attr = task.indicator.governs_attribute
    if attr:
        if attr in ['PWD', 'KP']:
            #these fields are tied to their own automatic model and are not currently supported
            return
        elif attr in ['PLWHIV']:
            hiv_status = HIVStatus.objects.filter(respondent=respondent).first()
            if hiv_status:
                if hiv_status.hiv_positive and instance.interaction_date != hiv_status.date_positive:
                    if not InteractionFlag.objects.filter(
                        interaction=instance,
                        reason__icontains="Marked as positive for HIV on a separate date"
                    ).exists():
                        InteractionFlag.objects.create(
                            interaction=instance,
                            auto_flagged=True,
                            reason=(
                                "Respondent was marked as testing positive for HIV, but was "
                                "already marked as positive for HIV on a separate date."
                            )
                        )
                else:
                    hiv_status.hiv_positive = True
                    hiv_status.date_positive = instance.interaction_date
                    hiv_status.save()
            else:
                HIVStatus.objects.create(
                    respondent=respondent,
                    hiv_positive=True,
                    date_positive=instance.interaction_date
                )
            #let the above signal handle the creation of the attribute type
        else:
            RespondentAttribute.objects.get_or_create(respondent=respondent, attribute=attr)

@receiver(post_save, sender=InteractionFlag)
def create_alert_on_flag(sender, instance, created, **kwargs):
    if not created:
        return

    # Determine recipients
    send_alert_to = User.objects.filter(
        Q(role='meofficer', organization=instance.interaction.task.organization) |
        Q(role='admin')
    ).distinct()

    # Create the alert
    content_type = ContentType.objects.get_for_model(Interaction)
    alert = Alert.objects.create(
        subject='Flag Raised',
        body=instance.reason,
        alert_type=Alert.AlertType.FLAG,
        content_type=content_type,
        object_id=instance.interaction.id
    )

    # Create AlertRecipient objects
    AlertRecipient.objects.bulk_create([
        AlertRecipient(alert=alert, recipient=user) for user in send_alert_to
    ])

@receiver(pre_save, sender=InteractionFlag)
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

        content_type = ContentType.objects.get_for_model(instance.interaction)
        alert = Alert.objects.create(
            subject='Flag Resolved',
            body=f"The following flag was resolved: {instance.reason}",
            alert_type=Alert.AlertType.FR, 
            content_type=content_type,
            object_id=instance.interaction.id
        )

        AlertRecipient.objects.bulk_create([
            AlertRecipient(alert=alert, recipient=user) for user in send_alert_to
        ])