from django.db.models import Q
from respondents.models import Interaction, InteractionFlag, HIVStatus, Pregnancy, InteractionSubcategory
from projects.models import Target
from events.models import DemographicCount, CountFlag
from itertools import product
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict

FIELD_MAP = {
    'kp_type': 'kp_status',
    'disability_type': 'disability_status',
    # others as needed
}

FILTERS_MAP = {
    'kp_type': 'kp_status__name',
    'disability_type': 'disability_status__name',
    # others as needed
}

def get_month_string(date):
    return date.strftime('%b %Y') 

def get_quarter_string(date):
    return f"Q{((date.month - 1) // 3) + 1} {date.year}"

def get_month_strings_between(start_date, end_date):
    months = []
    current = start_date.replace(day=1)
    while current <= end_date:
        months.append(get_month_string(current)) 
        current += relativedelta(months=1)
    return months

def get_quarter_strings_between(start_date, end_date):
    quarters = []
    current = start_date.replace(day=1)
    while current <= end_date:
        quarters.append(get_quarter_string(current))
        current += relativedelta(months=3)
    return quarters


#theoretically unnecessary to check other roles since the viewset should bar them
def get_interactions_from_indicator(user, indicator, project, organization, start, end, filters):
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
    if filters:
        for field, values in filters.items():
            if field == 'subcategory':
                continue #this has to be handled at a lower level
            elif field in ['pregnancy', 'hiv_status']:
                if len(values) == 2 or len(values) == 0:
                        continue
                respondent_ids = {i.respondent_id for i in queryset}
                if field == 'pregnancy':
                    pregnancies_map = get_pregnancies(respondent_ids)
                    preg_ids = [
                        interaction.id for interaction in queryset
                        if any(
                            p.term_began <= interaction.interaction_date <= (p.term_ended or date.today())
                            for p in pregnancies_map.get(interaction.respondent.id, [])
                        )
                    ]
                    if values[0] == 'Pregnant':
                        queryset = queryset.filter(id__in=preg_ids)
                    elif values[0] == 'Not_Pregnant':
                        queryset = queryset.exclude(id__in=preg_ids)
                if field == 'hiv_status':
                    hiv_status_map = get_hiv_statuses(respondent_ids)
                    pos_ids = [
                        interaction.id for interaction in queryset
                        if any(
                            hs.date_positive <= interaction.interaction_date
                            for hs in hiv_status_map.get(interaction.respondent.id, [])
                        )
                    ]
                    if values[0] == 'HIV_Positive':
                        queryset = queryset.filter(id__in=pos_ids)
                    elif values[0] == 'HIV_Negative':
                        queryset = queryset.exclude(id__in=pos_ids)
            elif field == 'citizenship':
                if len(values) == 2 or len(values) == 0:
                    continue
                if values[0] == 'citizen':
                    queryset = queryset.filter(respondent__citizenship='Motswana')
                elif values[0] == 'non_citizen':
                    queryset = queryset.exclude(respondent__citizenship='Motswana')
            else:
                field_name = FILTERS_MAP.get(field, field)
                if isinstance(values, list):
                    lookup = f"respondent__{field_name}__in"
                    queryset = queryset.filter(**{lookup: values})
                else:
                    queryset = queryset.filter(**{field_name: values})

    interaction_ids = queryset.values_list('id', flat=True)
    flags = InteractionFlag.objects.filter(interaction__id__in=interaction_ids)
    flagged_ids = flags.values_list('interaction_id', flat=True)
    return [obj for obj in queryset if obj.id not in flagged_ids]

def get_interaction_subcats(interactions):
    interaction_ids = [ir.id for ir in interactions]
    return InteractionSubcategory.objects.filter(interaction__id__in=interaction_ids)


def get_event_counts_from_indicator(user, indicator, params, project, organization, start, end, filters):
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
    if filters:
        for field, values in filters.items():
            if isinstance(values, list):
                lookup = f"{field}__in"
                queryset = queryset.filter(**{lookup: values})
            else:
                queryset = queryset.filter(**{field: values})
    count_ids = queryset.values_list('id', flat=True)
    flags = CountFlag.objects.filter(count__id__in=count_ids)
    flagged_ids = flags.values_list('count_id', flat=True)
    queryset  = [obj for obj in queryset if obj.id not in flagged_ids]
    #pre_exclude any count that does not match the requested breakdowns
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

def get_indicator_aggregate(user, indicator, params, split=None, project=None, organization=None, start=None, end=None, filters=None):
    interactions = get_interactions_from_indicator(user, indicator, project, organization, start, end, filters)
    counts = get_event_counts_from_indicator(user, indicator, params, project, organization, start, end, filters)
    fields_map = {}
    include_subcats=False
    for param, include in params.items():
        if include:
            if param == 'subcategory' and indicator.subcategories.exists():
                include_subcats = True
                fields_map['subcategory'] = [cat.name for cat in indicator.subcategories.all()]
                continue
            field = DemographicCount._meta.get_field(param)
            if field:
                fields_map[param] = [value for value, label in field.choices]
        
    period_func = get_quarter_string if split == 'quarter' else get_month_string
    periods = sorted({period_func(i.interaction_date) for i in interactions})

    if split in ['month', 'quarter']:
        fields_map['period'] = periods

    

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

    cartesian_product_sets = {frozenset(item) for item in cartesian_product}
    product_index_sets = {frozenset(k): v for k, v in product_index.items()}

    subcat_filter = None
    if filters:
        subcat_filter = filters.get('subcategory', None)

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
        if indicator.subcategories.exists() and include_subcats:
            interaction_subcats = subcats.filter(interaction=interaction)
            for cat in interaction_subcats:
                if subcat_filter:
                    if str(cat.subcategory.id) in subcat_filter:
                        continue
                combo = tuple(interaction_params + [cat.subcategory.name])
                permus.append(combo)
                if indicator.require_numeric:
                    numerics.append(cat.numeric_component)
        else:
            combo = tuple(interaction_params)
            permus.append(combo)
            if indicator.subcategories.exists() and indicator.require_numeric and not include_subcats:
                total = 0
                interaction_subcats = subcats.filter(interaction=interaction)
                for cat in interaction_subcats:
                    if subcat_filter:
                        if str(cat.subcategory.id) in subcat_filter:
                            continue
                    total += cat.numeric_component
                numerics.append(total)
            elif indicator.require_numeric:
                numerics.append(interaction.numeric_component)
        

        for i, combination in enumerate(permus):
            combo_set = frozenset(combination)
            if combo_set in cartesian_product_sets:
                pos = product_index_sets.get(combo_set)
                if pos is not None:
                    amount = numerics[i] if numerics else 1
                    aggregates[pos]['count'] += amount


    for count in counts:
        count_params = []
        for field in fields_map.keys():
            if field == 'period':   
                field_val=None
            else:
                field_val = getattr(count, field)
            if field == 'subcategory':
                field_val = field_val.name 
            if field_val: 
                count_params.append(field_val)
        if split in ['month', 'quarter']:
            count_params.append(period_func(count.event.event_date))

        param_set = frozenset(count_params)
        if param_set in cartesian_product_sets:
            pos = product_index_sets.get(param_set)
            if pos is not None:
                aggregates[pos]['count'] += count.count
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

def get_target_aggregates(user, indicator, split, start=None, end=None, project=None, organization=None):
    queryset = Target.objects.filter(task__indicator=indicator)

    if user.role not in ['admin', 'client']:
        queryset = queryset.filter(
            Q(task__organization=user.organization) |
            Q(task__organization__parent_organization=user.organization)
        )

    if project:
        queryset = queryset.filter(task__project=project)
    if organization:
        queryset = queryset.filter(task__organization=organization)
    if start:
        queryset = queryset.filter(interaction_date__gte=start)
    if end:
        queryset = queryset.filter(interaction_date__lte=end)

    targets_map = defaultdict(float)

    range_func = get_quarter_strings_between if split == 'quarter' else get_month_strings_between

    for target in queryset:
        amount = target.amount
        if not amount and target.related_to and target.percentage_of_related:
            amount = round(
                Interaction.objects.filter(
                    task=target.related_to,
                    interaction_date__gte=target.start,
                    interaction_date__lte=target.end
                ).count() * (target.percentage_of_related / 100)
            )

        if not amount or not target.start or not target.end:
            continue

        periods = range_func(target.start, target.end)
        for period in periods:
            targets_map[period] += round(amount / len(periods))

    return dict(targets_map)
        


