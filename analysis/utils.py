from django.db.models import Q
from respondents.models import Interaction, InteractionFlag, HIVStatus, Pregnancy, InteractionSubcategory
from events.models import DemographicCount, CountFlag
from itertools import product
from datetime import date

FIELD_MAP = {
    'kp_type': 'kp_status',
    'disability_type': 'disability_status',
    # others as needed
}

#theoretically unnecessary to check other roles since the viewset should bar them
def get_interactions_from_indicator(user, indicator):
    queryset = Interaction.objects.filter(task__indicator=indicator)
    if user.role not in ['admin', 'client']:
        queryset=queryset.filter(Q(task__organization=user.organization)|Q(task__organization__parent_organization=user.organization))
    interaction_ids = queryset.values_list('id', flat=True)
    flags = InteractionFlag.objects.filter(interaction__id__in=interaction_ids)
    flagged_ids = flags.values_list('interaction_id', flat=True)
    return [obj for obj in queryset if obj.id not in flagged_ids]

def get_interaction_subcats(interactions):
    interaction_ids = [ir.id for ir in interactions]
    return InteractionSubcategory.objects.filter(interaction__id__in=interaction_ids)


def get_counts_from_indicator(user, indicator, params):
    queryset = DemographicCount.objects.filter(task__indicator=indicator)
    if user.role not in ['admin', 'client']:
        queryset=queryset.filter(Q(task__organization=user.organization) | Q(task__organization__parent_organization=user.organization))
    count_ids = queryset.values_list('id', flat=True)
    flags = CountFlag.objects.filter(count__id__in=count_ids)
    flagged_ids = flags.values_list('count_id', flat=True)
    queryset  = [obj for obj in queryset if obj.id not in flagged_ids]
    #pre_exclude any count that does not match the requested breakdowns
    for field, should_exist in params.items():
        if should_exist:
            query |= Q(**{f"{field}__isnull": True})
    queryset = queryset.exclude(query)
    return queryset

def get_pregnancies(respondent_ids):
    pregnancies = Pregnancy.objects.filter(respondent_id__in=respondent_ids)

    pregnancies_by_respondent = {}
    for p in pregnancies:
        if p and p.term_began:
            pregnancies_by_respondent.setdefault(p.respondent_id, []).append(p)
    return pregnancies_by_respondent

def get_hiv_statuses(respondent_ids):
    hiv_statuses = HIVStatus.objects.filter(respondent_id__in=respondent_ids)
    hiv_status_by_respondent = {}
    for hs in hiv_statuses:
        if hs and hs.date_positive:
            hiv_status_by_respondent.setdefault(hs.respondent_id, []).append(hs)
    return hiv_status_by_respondent

def get_indicator_aggregate(user, indicator, params):
    interactions = get_interactions_from_indicator(user, indicator)
    #counts = get_counts_from_indicator(user, indicator, params)
    fields_map = {}
    for param, include in params.items():
        if include:
            field = DemographicCount._meta.get_field(param)
            fields_map[param] = [value for value, label in field.choices]
    
    if indicator.subcategories.exists():
        fields_map['subcategories'] = [cat.name for cat in indicator.subcategories.all()]

    #fields_map = {age_range: [18-24, 25-34...], sex: ['Male', 'Female]}

    cartesian_product = list(product(*[bd for bd in fields_map.values()]))
    #[(18-24, M), (18-24, F)]

    product_index = {tuple(p): i for i, p in enumerate(cartesian_product)}

    aggregates = {}
    for pos, arr in enumerate(cartesian_product):
        aggregates[pos] = {}
        for i, field in enumerate(fields_map.keys()):
            aggregates[pos][field] = arr[i]
        aggregates[pos]['count'] = 0
    #{1: {age_range: 18-24, sex: M}, 2: {age_range: 18-24, sex: F}}

    respondent_ids = {i.respondent_id for i in interactions}
    hiv_status_map = get_hiv_statuses(respondent_ids=respondent_ids)
    pregnancies_map = get_pregnancies(respondent_ids=respondent_ids)
    subcats = get_interaction_subcats(interactions)

    for interaction in interactions:
        include = False
        interaction_params = []
        for field in fields_map.keys():
            get_field = FIELD_MAP.get(field, field)
            if field == 'pregnancy':
                field_val = 'Pregnant' if any(
                    p.term_began <= interaction.interaction_date <= p.term_ended if p.term_ended else date.today()
                    for p in pregnancies_map.get(interaction.respondent.id, [])
                ) else 'Not Pregnant'
            elif field == 'hiv_status':
                field_val = 'HIV Positive' if any(
                    hs. date_positive <= interaction.interaction_date
                    for hs in hiv_status_map.get(interaction.respondent.id, [])
                ) else 'HIV Negative'
            elif field == 'subcategories':
                field_val = None
            else:
                field_val = getattr(interaction.respondent, get_field)
                if field == 'citizenship':
                    field_val = 'Citizen' if field_val == 'Motswana' else 'Non-Citizen'
            if field_val:
                interaction_params.append(field_val)
        permus = []
        numerics = []
        if indicator.subcategories.exists():
            interaction_subcats = subcats.filter(interaction=interaction)
            for cat in interaction_subcats:
                combo = tuple(interaction_params + [cat.subcategory.name])
                permus.append(combo)
                if indicator.require_numeric:
                    numerics.append(cat.numeric_component)
        else:
            combo = tuple(interaction_params)
            permus.append(combo)
            if indicator.require_numeric:
                numerics.append(interaction.numeric_component)
        for i, combination in enumerate(permus):
            if combination in cartesian_product:
                pos = product_index.get(tuple(combination))
                if pos is not None:
                    amount = numerics[i] if numerics else 1
                    aggregates[pos]['count'] += amount
    return aggregates

    
def prep_csv(aggregates, params):
    column_field = next((k for k, v in params.items() if v), None)
    #age_range
    column_field_choices = [value for value, label in DemographicCount._meta.get_field(column_field).choices]
    #[18-24, 25-34]
    fields = [field for field in aggregates[0].keys() if field not in ['count', column_field]]
    row1 = fields + column_field_choices
    #Sex, Subcategory, 18-24, 25-34
    rows_map = {}
    for cell in aggregates.values():
        breakdowns = [cell[k] for k in cell if k not in ['count', column_field]]
        breakdowns_key = '__'.join(str(val).replace(' ', '_') for val in breakdowns)
        #Male, Cat 1
        column_field_value = cell[column_field]
        col = row1.index(column_field_value)
        count = cell['count']
        if not rows_map.get(breakdowns_key):
            rows_map[breakdowns_key] = {}
        rows_map[breakdowns_key][col] = count 
    #rows {male__cat_1: {4: 22}, {3: 6}}
    rows = [row1]
    for key, value in rows_map.items():
        row = key.split('__')
        counts = []
        for column, count in value.items():
            counts.append(count)
        row += counts
        #row = [male, cat_1, 6, 22]
        rows.append(row)
    print(rows)
    return rows



        


