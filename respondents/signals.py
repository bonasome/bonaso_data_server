from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from respondents.models import KeyPopulationStatus, DisabilityStatus, HIVStatus, RespondentAttribute, RespondentAttributeType
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