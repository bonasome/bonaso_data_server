def get_breakdown_keys(count):
    # Only include keys that are part of the breakdown schema
    return frozenset(k for k in count if k not in ['count', 'task_id'])

BREAKDOWN_FIELDS = [
    'sex', 'age_range', 'citizenship', 'hiv_status', 'pregnancy',
    'disability_type', 'kp_type', 'status', 'subcategory_id', 'organization_id'
]

def get_schema_key(counts):
    # Find all fields that actually appear across all counts
    keys = set()
    for count in counts:
        keys.update(k for k in BREAKDOWN_FIELDS if k in count and count[k] not in [None, ''])
    return frozenset(keys)

def make_key(data, schema_keys):
    return tuple((k, data.get(k)) for k in schema_keys)