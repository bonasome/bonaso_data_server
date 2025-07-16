from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from respondents.models import KeyPopulationStatus, DisabilityStatus, HIVStatus, RespondentAttribute, RespondentAttributeType, InteractionFlag, Interaction
from django.db import transaction

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
def handle_hiv_positive_interaction(sender, instance, created, **kwargs):
    if not created:
        return  # Only run on creation

    task = instance.task
    respondent = instance.respondent

    if not task or not respondent:
        return

    if task.indicator.name == 'Tested Positive for HIV':
        hiv_status = HIVStatus.objects.filter(respondent=respondent).first()

        if hiv_status:
            if hiv_status.hiv_positive and instance.interaction_date != hiv_status.date_positive:
                if not InteractionFlag.objects.filter(
                    interaction=instance,
                    reason__icontains="marked as positive for HIV on a separate date"
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