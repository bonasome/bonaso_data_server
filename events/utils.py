from events.models import DemographicCount
from flags.utils import create_flag, resolve_flag

'''
Few utils to help with checking count breakdown fields
'''
BREAKDOWN_FIELDS = [
    'sex', 'age_range', 'citizenship', 'hiv_status', 'pregnancy',
    'disability_type', 'kp_type', 'status', 'subcategory_id', 'organization_id'
]

def get_breakdown_keys(count):
    # Only include keys that are part of the breakdown schema
    return frozenset(k for k in count if k not in ['count', 'task_id'])

def get_schema_key(counts):
    # Find all fields that actually appear across all counts
    keys = set()
    for count in counts:
        keys.update(k for k in BREAKDOWN_FIELDS if k in count and count[k] not in [None, ''])
    return frozenset(keys)

def make_key(data, schema_keys):
    #create a unique key that represents a count to verfiy duplicates
    return tuple((k, data.get(k)) for k in schema_keys)

def count_flag_logic(instance, user):
    '''
    Check if event has a prerequisite and if not or the counts do not align (i.e., more people tested positive than tested),
    throw a flag.
    '''
    existing_flags = instance.flags
    task = instance.task
    #check if there is a prerequisite count if required
    if task.indicator.prerequisites:
        for prereq in task.indicator.prerequisites.all():
            prerequisite_count = DemographicCount.objects.filter(
                event=instance.event,
                task__indicator=prereq,
                sex=instance.sex,
                age_range=instance.age_range,
                citizenship=instance.citizenship,
                hiv_status=instance.hiv_status,
                pregnancy=instance.pregnancy,
                disability_type=instance.disability_type,
                kp_type=instance.kp_type,
                subcategory=instance.subcategory,
                organization=instance.organization,
                status=instance.status
            ).first()

            reason = f'Task "{task.indicator.name}" has a prerequisite "{prereq.name}" that does not have an associated count.'
            if not prerequisite_count:
                already_flagged = existing_flags.filter(reason=reason).exists()
                if not already_flagged:
                    create_flag(instance, reason, user)
            else:
                outstanding_flag = existing_flags.filter(reason=reason, resolved=False).first()
                if outstanding_flag:
                    resolve_flag(existing_flags, reason)

            #also flag it if the count is higher than the prerequisite count (i.e., more people shouldn't test positive for HIV than were tested for HIV)
            reason=f'The amount of this count is greater than its corresponding prerequisite "{prereq.name}" amount.'
            if prerequisite_count and prerequisite_count.count < instance.count:
                already_flagged = existing_flags.filter(reason=reason).exists()
                if not already_flagged:
                    create_flag(instance, reason, user)
            else:
                resolve_flag(existing_flags, reason)