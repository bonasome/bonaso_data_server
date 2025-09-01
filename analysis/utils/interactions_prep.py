from datetime import date
from analysis.utils.periods import get_month_string, get_quarter_string

#convert names as they appear in the demographic count model/filters to how they appear on the respondent model
FIELD_MAP = {
    'kp_type': 'kp_status',
    'disability_type': 'disability_status',
    # Add more if needed
}

# convert m2m fields into the name so the filter function returns the correct value
M2M_MAP = {
    'kp_type': 'kp_status__name',
    'disability_type': 'disability_status__name',
    'special_attribute': 'special_attribute__name',
}

#list of valid fields to pull by, make sure this is updated if any demographic splits are added or removed
fields = ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy', 'organization']

def build_keys(interaction, pregnancies_map, hiv_status_map, interaction_subcats, include_subcats):
    """
    Returns dict mapping frozenset keys -> numeric values (default to 1 if no subcats/numeric)
    - interaction (interaction instance): interaction to build keys for
    - pregnancies_map (dict): helper object that can rapidly look up if an interaction's respondent was pregnant
    - hiv_status_map (dict): helper object that can rapidly look up a respondent's HIV status
    - interaction_subcats (queryset): queryset of interaction subcategory objects that were prefetched and can be referenced
    - include_subcats (boolean): if this is being broken down by subcats that require a numeric value, each numeric value
        must appear as a seperate key so it can be added to the correct bucket
    """
    #create base empty key that we will add to
    base_keys = set()

    # go through each field and pull the correct value and add it to keys
    for field in fields:
        get_field = FIELD_MAP.get(field, field)
        
        if field == 'organization':
            base_keys.add(interaction.task.organization.name)
        elif field == 'pregnancy':
            is_pregnant = any(
                p.term_began <= interaction.interaction_date <= (p.term_ended or date.today())
                for p in pregnancies_map.get(interaction.respondent.id, [])
            )
            base_keys.add('pregnant' if is_pregnant else 'not_pregnant')

        elif field == 'hiv_status':
            is_positive = any(
                hs.date_positive <= interaction.interaction_date
                for hs in hiv_status_map.get(interaction.respondent.id, [])
            )
            base_keys.add('hiv_positive' if is_positive else 'hiv_negative')

        #if its an M2M field, add all the values to the keys, the parent will check if its a subset
        elif field in M2M_MAP:
            m2m_field = getattr(interaction.respondent, FIELD_MAP[field])
            base_keys.update(m2m_field.values_list('name', flat=True))  # assumes prefetched
        else:
            val = getattr(interaction.respondent, get_field)
            if field == 'citizenship':
                val = 'citizen' if val and val.lower() == 'bw' else 'non_citizen'
            base_keys.add(val)
        base_keys.add(get_month_string(interaction.interaction_date))
        base_keys.add(get_quarter_string(interaction.interaction_date))
    keys = {}

    # Case: no subcat split/subcat does not have a number, in either case returning one key works 
    # if no subcat is required, we can treat this as one combined unit with one lump sum
    # if subcat is required, but there is no number, we can combine it as one key since the value will alwasy be 1
    if not include_subcats or not interaction.task.indicator.require_numeric:
        key = frozenset(base_keys)
        if interaction.task.indicator.subcategories.exists():
            amount = 0
            subcat_names = set()

            for cat in interaction_subcats.filter(interaction=interaction):
                if interaction.task.indicator.require_numeric:
                    amount += cat.numeric_component or 0
                subcat_names.add(cat.subcategory.name)
            if not interaction.task.indicator.require_numeric:
                amount = 1
            key = frozenset(key | subcat_names)
        elif interaction.task.indicator.require_numeric:
            amount = interaction.numeric_component or 0
        else:
            amount = 1
        keys[key] = amount
        return keys

    # Case: subcat split and number required, in which case each key will have a differnet value that needs to be added
    for cat in interaction_subcats.filter(interaction=interaction):
        key = frozenset(base_keys | {cat.subcategory.name})
        keys[key] = cat.numeric_component or 0

    return keys
