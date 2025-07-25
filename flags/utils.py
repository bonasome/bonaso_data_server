from django.utils.timezone import now
from django.contrib.contenttypes.models import ContentType

from flags.models import Flag

def create_flag(instance, reason, caused_by):
    Flag.objects.create(
        content_type=ContentType.objects.get_for_model(instance),
        object_id = instance.id,
        reason=reason,
        auto_flagged=True,
        caused_by=caused_by
    )
def resolve_flag(flags_qs, reason):
    to_resolve = flags_qs.filter(reason=reason, auto_flagged=True, resolved=False).first()
    if to_resolve:
        to_resolve.resolved = True
        to_resolve.auto_resolved = True
        to_resolve.resolved_at = now()
        to_resolve.save()