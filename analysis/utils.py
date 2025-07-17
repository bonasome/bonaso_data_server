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

def get_month_string(date):
    return date.strftime('%b %Y')  # e.g., "Jul 2025"

def get_quarter_string(date):
    return f"Q{((date.month - 1) // 3) + 1} {date.year}"


#theoretically unnecessary to check other roles since the viewset should bar them
def get_interactions_from_indicator(user, indicator, project, organization, start, end):
    queryset = Interaction.objects.filter(task__indicator=indicator)
    if user.role not in ['admin', 'client']:
        queryset=queryset.filter(Q(task__organization=user.organization)|Q(task__organization__parent_organization=user.organization))
    if project:
        queryset=queryset.filter(task__project=project)
    if organization:
        queryset=queryset.filter(task__organization=organization)
    if start:
        queryset=queryset.filter(interaction_date__gte=start)
    if end:
        queryset=queryset.filter(interaction_date__lte=end)
    interaction_ids = queryset.values_list('id', flat=True)
    flags = InteractionFlag.objects.filter(interaction__id__in=interaction_ids)
    flagged_ids = flags.values_list('interaction_id', flat=True)
    return [obj for obj in queryset if obj.id not in flagged_ids]

def get_interaction_subcats(interactions):
    interaction_ids = [ir.id for ir in interactions]
    return InteractionSubcategory.objects.filter(interaction__id__in=interaction_ids)


def get_event_counts_from_indicator(user, indicator, params, project, organization, start, end):
    query = Q()
    for field, should_exist in params.items():
        if should_exist:
            query |= Q(**{f"{field}__isnull": True})

    queryset = DemographicCount.objects.filter(task__indicator=indicator)
    if project:
        queryset=queryset.filter(task__project=project)
    if organization:
        queryset=queryset.filter(task__organization=organization)
    if start:
        queryset=queryset.filter(event__event_date__gte=start)
    if end:
        queryset=queryset.filter(event__event_date__lte=end)
    if user.role not in ['admin', 'client']:
        queryset=queryset.filter(Q(task__organization=user.organization) | Q(task__organization__parent_organization=user.organization))
    count_ids = queryset.values_list('id', flat=True)
    flags = CountFlag.objects.filter(count__id__in=count_ids)
    flagged_ids = flags.values_list('count_id', flat=True)
    queryset  = [obj for obj in queryset if obj.id not in flagged_ids]
    #pre_exclude any count that does not match the requested breakdowns
    print(queryset)
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

def get_indicator_aggregate(user, indicator, params, split=None, project=None, organization=None, start=None, end=None):
    interactions = get_interactions_from_indicator(user, indicator, project, organization, start, end)
    counts = get_event_counts_from_indicator(user, indicator, params, project, organization, start, end)
    fields_map = {}
    print(params)
    for param, include in params.items():
        if include:
            field = DemographicCount._meta.get_field(param)
            if field:
                fields_map[param] = [value for value, label in field.choices]
        
    period_func = get_quarter_string if split == 'quarter' else get_month_string
    periods = sorted({period_func(i.interaction_date) for i in interactions})

    if split in ['month', 'quarter']:
        fields_map['period'] = periods

    if indicator.subcategories.exists():
        fields_map['subcategory'] = [cat.name for cat in indicator.subcategories.all()]

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
                ) else 'Not_Pregnant'
            elif field == 'hiv_status':
                field_val = 'HIV_Positive' if any(
                    hs. date_positive <= interaction.interaction_date
                    for hs in hiv_status_map.get(interaction.respondent.id, [])
                ) else 'HIV_Negative'
            elif field == 'subcategory':
                field_val = None
            elif field == 'period':
                field_val = None
            else:
                field_val = getattr(interaction.respondent, get_field)
                if field == 'citizenship':
                    field_val = 'Citizen' if field_val == 'Motswana' else 'Non-Citizen'
            if field_val:
                interaction_params.append(field_val)
        if split in ['month', 'quarter']:
            interaction_params.append(period_func(interaction.interaction_date))
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
            print(combination)
            if combination in cartesian_product:
                pos = product_index.get(tuple(combination))
                if pos is not None:
                    amount = numerics[i] if numerics else 1
                    aggregates[pos]['count'] += amount

    for count in counts:
        count_params = []
        for field in fields_map.keys():
            if field == 'period':
                field_val=None
            else:
                field_val = getattr(count, get_field)
            count_params.append(field_val)
        if split in ['month', 'quarter']:
            print(period_func(count.event.event_date))
            count_params.append(period_func(count.event.event_date))
        if combination in cartesian_product:
            pos = product_index.get(tuple(combination))
            if pos is not None:
                aggregates[pos]['count'] += count.count

    print(aggregates)
    return aggregates
    
def prep_csv(aggregates, params):
    column_field = next((k for k, v in params.items() if v), None)
    column_field_choices = sorted({cell[column_field] for cell in aggregates.values()})

    # Dynamically extract all fields that are not 'count' or column_field
    fields = [f for f in list(aggregates.values())[0].keys() if f not in ['count', column_field]]
    row1 = fields + column_field_choices  # CSV header: breakdown fields + dynamic columns

    rows_map = {}
    for cell in aggregates.values():
        breakdowns = tuple(cell[k] for k in fields)  # Tuple of breakdown values in defined order
        column_field_value = cell[column_field]
        count = cell['count']

        if breakdowns not in rows_map:
            rows_map[breakdowns] = {}

        rows_map[breakdowns][column_field_value] = count

    # Build final rows
    rows = [row1]
    for breakdown_values, counts_dict in rows_map.items():
        row = list(breakdown_values)
        for col_val in column_field_choices:
            row.append(counts_dict.get(col_val, 0))  # default to 0 if missing
        rows.append(row)

    return rows



        


