from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.db.models import Q
from respondents.models import KeyPopulationStatus, DisabilityStatus, HIVStatus, RespondentAttribute, RespondentAttributeType, Interaction, Respondent
from django.db import transaction
from messaging.models import Alert, AlertRecipient
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
User = get_user_model()


def update_attribute(respondent, attribute_enum, should_add):
    '''
    Helper function that helps automatic attribute syncs set the correct respondent and attribute.
        -should_add -> determines if this attribute is new and should be added or was removed and should be deleted
    '''
    try:
        #make sure that the attribute type is valid
        attr_type, _ = RespondentAttributeType.objects.get_or_create(name=attribute_enum)
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

'''
Below functions are all for updating special attributes that can be used to help with interaction checks.
'''
# === Key Population === #
@receiver(post_save, sender=KeyPopulationStatus)
@receiver(post_delete, sender=KeyPopulationStatus)
def sync_kp_attribute(sender, instance, **kwargs):
    '''
    If a respondent KP status is edited, automatically update their attribute status as a KP.
    '''
    respondent = instance.respondent
    def after_commit():
        should_add = KeyPopulationStatus.objects.filter(respondent=respondent).exists()
        update_attribute(respondent, RespondentAttributeType.Attributes.KP, should_add)

    transaction.on_commit(after_commit)


# === Disability ===
@receiver(post_save, sender=DisabilityStatus)
@receiver(post_delete, sender=DisabilityStatus)
def sync_disability_attribute(sender, instance, **kwargs):
    '''
    If a respondent KP status is edited, automatically update their attribute status to PWD.
    '''
    respondent = instance.respondent
    def after_commit():
        should_add = DisabilityStatus.objects.filter(respondent=respondent).exists()
        update_attribute(respondent, RespondentAttributeType.Attributes.PWD, should_add)
    transaction.on_commit(after_commit)


# === HIV Status ===
@receiver(post_save, sender=HIVStatus)
@receiver(post_delete, sender=HIVStatus)
def sync_hiv_attribute(sender, instance, **kwargs):
    '''
    If a respondent's HIV status changes, update the corresponding attribute.
    '''
    respondent = instance.respondent
    def after_commit():
        should_add = HIVStatus.objects.filter(respondent=respondent, hiv_positive=True).exists()
        update_attribute(respondent, RespondentAttributeType.Attributes.PLWHIV, should_add)
    transaction.on_commit(after_commit)

@receiver(post_save, sender=Interaction)
def handle_govern_interaction(sender, instance, created, **kwargs):
    '''
    Some indicators may be associated with respondent attributes that we want to automatically update
    (i.e., indicator tested postiive for HIV --> automatically mark person as HIV positive if they are not.)
    This isn't super fleshed out, and was mostly created for the above scenario, but could be expanded to other things
    in the future. 

    instance --> interaction in question (links to indicator and respondent)
    created --> is this a create or an update. Interaction updates should not retrigger this, only creation.
    '''
    if not created:
        return 

    task = instance.task
    respondent = instance.respondent

    if not task or not respondent:
        return

    attr = task.indicator.governs_attribute
    if attr:
        #these fields are tied to their own automatic model and are not currently supported
        if attr in ['PWD', 'KP']:
            return
        #update respondent HIV status
        elif attr in ['PLWHIV']:
            hiv_status = HIVStatus.objects.filter(respondent=respondent).first()
            if hiv_status:
                #if the status was already known, return
                if hiv_status.hiv_positive:
                    return
                #otherwise update the status
                else:
                    hiv_status.hiv_positive = True
                    hiv_status.date_positive = instance.interaction_date
                    hiv_status.save()
            #create new status
            else:
                HIVStatus.objects.create(
                    respondent=respondent,
                    hiv_positive=True,
                    date_positive=instance.interaction_date
                )
        #otherwise create the link object
        else:
            RespondentAttribute.objects.get_or_create(respondent=respondent, attribute=attr)
