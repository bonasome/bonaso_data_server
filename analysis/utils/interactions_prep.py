from datetime import date

FIELD_MAP = {
    'kp_type': 'kp_status',
    'disability_type': 'disability_status',
    # Add more if needed
}

M2M_MAP = {
    'kp_type': 'kp_status__name',
    'disability_type': 'disability_status__name',
    'special_attribute': 'special_attribute__name',
}

fields = ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy', 'organization']
from analysis.utils.periods import get_month_string, get_quarter_string
def build_keys(interaction, pregnancies_map, hiv_status_map, interaction_subcats, include_subcats):
    """
    Returns dict mapping frozenset keys -> numeric values (default to 1 if no subcats/numeric)
    """
    base_keys = set()

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

        elif field in M2M_MAP:
            m2m_field = getattr(interaction.respondent, FIELD_MAP[field])
            base_keys.update(m2m_field.values_list('name', flat=True))  # assumes prefetched
        else:
            val = getattr(interaction.respondent, get_field)
            if field == 'citizenship':
                val = 'citizen' if val and val.lower() == 'motswana' else 'non_citizen'
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
