from django.db.models import Q
from respondents.models import Interaction
from projects.models import Target, ProjectOrganization
from events.models import DemographicCount, Event
from itertools import product
from datetime import date
from collections import defaultdict

from analysis.utils.collection import get_event_counts_from_indicator, get_interactions_from_indicator, get_hiv_statuses, get_pregnancies, get_interaction_subcats, get_events_from_indicator, get_posts_from_indicator
from analysis.utils.periods import get_month_string, get_quarter_string, get_month_strings_between, get_quarter_strings_between

#map to convert some of the different field names from the respondent/count model
FIELD_MAP = {
    'kp_type': 'kp_status',
    'disability_type': 'disability_status',
    # others as needed
}

def demographic_aggregates(user, indicator, params, split=None, project=None, organization=None, start=None, end=None, filters=None):
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
            elif param == 'subcategory':
                print('WARNING: This indicator has no subcategories.')
                continue
            field = DemographicCount._meta.get_field(param)
            if field:
                print(param)
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
                    field_val = 'citizen' if field_val == 'Motswana' else 'non-citizen'
            if field_val:
                interaction_params.append(field_val)
        print(interaction_params)
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

def event_no_aggregates(user, indicator, split, project, organization, start, end):
    events = get_events_from_indicator(user, indicator, project, organization, start, end)
    print('event_no', len(events))
    aggregates = defaultdict(int)

    if split in ['month', 'quarter']:
        by_period = defaultdict(int)
        period_func = get_quarter_string if split == 'quarter' else get_month_string

        for event in events:
            period = period_func(event.start)
            by_period[period] += 1
            aggregates['count'] += 1  # total count across periods

        aggregates['by_period'] = dict(by_period)

    else:
        aggregates['count'] = len(events)

    return dict(aggregates)

    

def event_org_no_aggregates(user, indicator, split, project, organization, start, end):
    events = get_events_from_indicator(user, indicator, project, organization, start, end)
    print('event_org_no', len(events))
    aggregates = defaultdict(int)

    if split in ['month', 'quarter']:
        by_period = defaultdict(int)
        period_func = get_quarter_string if split == 'quarter' else get_month_string

        for event in events:
            org_count = event.organizations.count()
            period = period_func(event.start)
            by_period[period] += org_count
            aggregates['count'] += org_count  # total count across periods

        aggregates['by_period'] = dict(by_period)

    else:
        aggregates['count'] += sum(event.organizations.count() for event in events)

    return dict(aggregates)

def social_aggregates(user, indicator, split, project, organization, start, end, platform):
    posts = get_posts_from_indicator(user, indicator, project, organization, platform, start, end)
    aggregates = defaultdict(int)

    if split in ['month', 'quarter']:
        by_period = defaultdict(lambda: defaultdict(int))
        period_func = get_quarter_string if split == 'quarter' else get_month_string

        for post in posts:
            likes = post.likes or 0
            views = post.views or 0
            comments = post.comments or 0
            period = period_func(post.published_at or date.fromtimestamp(post.created_at))

            by_period[period]['likes'] += likes
            by_period[period]['views'] += views
            by_period[period]['comments'] += comments
            by_period[period]['total_engagement'] += (likes + views + comments)

            aggregates['likes'] += likes
            aggregates['views'] += views
            aggregates['comments'] += comments
            aggregates['total_engagement'] += (likes + views + comments)

        aggregates['by_period'] = {k: dict(v) for k, v in by_period.items()}

    else:
        aggregates['likes'] += sum(post.likes or 0 for post in posts)
        aggregates['views'] += sum(post.views or 0 for post in posts)
        aggregates['comments'] += sum(post.comments or 0 for post in posts)
        aggregates['total_engagement'] += sum((post.likes or 0) + (post.views or 0) + (post.comments or 0) for post in posts)

    return dict(aggregates)

def aggregates_switchboard(user, indicator, params, split=None, project=None, organization=None, start=None, end=None, filters=None, platform=None):
    aggregates = {}
    if indicator.indicator_type == 'respondent' or indicator.indicator_type=='count':
        aggregates = demographic_aggregates(user, indicator, params, split, project, organization, start, end, filters)
    if indicator.indicator_type == 'event_no':
        aggregates = event_no_aggregates(user, indicator, split, project, organization, start, end)
    if indicator.indicator_type == 'event_org_no':
        aggregates = event_org_no_aggregates(user, indicator, split, project, organization, start, end)
    if indicator.indicator_type == 'social':
        aggregates = social_aggregates(user, indicator, split, project, organization, start, end, platform)
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
        child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
        queryset = queryset.filter(
                Q(task__organization=user.organization) | Q(task__organization__in=child_orgs)
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
        


