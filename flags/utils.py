from django.utils.timezone import now
from django.contrib.contenttypes.models import ContentType
from django.apps import apps

from flags.models import Flag

def create_flag(instance, reason, caused_by, reason_type=Flag.FlagReason.OTHER):
    '''
    Helper function that creates an auto-generated flag.
    '''
    Flag.objects.create(
        content_type=ContentType.objects.get_for_model(instance),
        object_id = instance.id,
        reason_type=reason_type,
        reason=reason,
        auto_flagged=True,
        caused_by=caused_by
    )
def resolve_flag(flags_qs, reason):
    '''
    Helper function that automatically resolves flags if the issue is fixed (for system generated).
    '''
    to_resolve = flags_qs.filter(reason=reason, auto_flagged=True, resolved=False).first()
    if to_resolve:
        to_resolve.resolved = True
        to_resolve.auto_resolved = True
        to_resolve.resolved_at = now()
        to_resolve.save()

def get_object_from_str(model_str: str, object_id: int):
    try:
        app_label, model_name = model_str.lower().split('.')
        model = apps.get_model(app_label, model_name)
        if not model:
            return None
        return model.objects.get(pk=object_id)
    except (ValueError, LookupError, model.DoesNotExist):
        return None