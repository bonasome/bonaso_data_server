from datetime import date
from analysis.utils.periods import get_month_string, get_quarter_string
from indicators.models import Indicator
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
fields = ['age_range', 'sex', 'kp_type', 'disability_type', 'citizenship', 'hiv_status', 'pregnancy', 'organization', 'option', 'district']

def build_keys(response, pregnancies_map, hiv_status_map):
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
            base_keys.add(response.interaction.task.organization.name)
        elif field == 'option':
            # add response option name if option breakdown is requested
            if response.response_option:
                base_keys.add(response.response_option.name) 
        elif field == 'pregnancy':
            is_pregnant = any(
                p.term_began <= response.response_date <= (p.term_ended or date.today())
                for p in pregnancies_map.get(response.interaction.respondent.id, [])
            )
            base_keys.add('pregnant' if is_pregnant else 'not_pregnant')

        elif field == 'hiv_status':
            is_positive = any(
                hs.date_positive <= response.response_date
                for hs in hiv_status_map.get(response.interaction.respondent.id, [])
            )
            base_keys.add('hiv_positive' if is_positive else 'hiv_negative')

        #if its an M2M field, add all the values to the keys, the parent will check if its a subset
        elif field in M2M_MAP:
            m2m_field = getattr(response.interaction.respondent, FIELD_MAP[field])
            base_keys.update(m2m_field.values_list('name', flat=True))  # assumes prefetched
        else:
            val = getattr(response.interaction.respondent, get_field)
            if field == 'citizenship':
                val = 'citizen' if val and val.lower() == 'bw' else 'non_citizen'
            base_keys.add(val)
        base_keys.add(get_month_string(response.response_date))
        base_keys.add(get_quarter_string(response.response_date))
    keys = {}

    key = frozenset(base_keys)
    amount = 0
    #if this is indicator collects a number, add the number for a sum (or average), otherwise add one for a count
    if response.indicator.type in [Indicator.Type.INT, Indicator.Type.MULTINT]:
        try:
            amount = int(response.response_value)
        except:
            print('Warning, invalid value.')
    else:
        amount = 1
    keys[key] = amount
    return keys
