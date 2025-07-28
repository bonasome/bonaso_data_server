from django.db.models import Q
from respondents.models import Interaction
from projects.models import Target, ProjectOrganization
from events.models import DemographicCount, Event
from itertools import product
from datetime import date
from collections import defaultdict
from indicators.models import Indicator
from analysis.utils.collection import get_event_counts_from_indicator, get_interactions_from_indicator, get_hiv_statuses, get_pregnancies, get_interaction_subcats, get_events_from_indicator, get_posts_from_indicator
from analysis.utils.periods import get_month_string, get_quarter_string, get_month_strings_between, get_quarter_strings_between
from analysis.utils.interactions_prep import build_keys

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
    periods = sorted({period_func(i.interaction_date) for i in interactions}) + sorted({period_func(count.event.end) for count in counts})

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

    subcat_filter = None
    if filters:
        subcat_filter = filters.get('subcategory', None)

    subcats = get_interaction_subcats(interactions, subcat_filter)

    product_index_sets = {frozenset(k): v for k, v in product_index.items()}

    for interaction in interactions:
        keys = build_keys(interaction, pregnancies_map, hiv_status_map, subcats, include_subcats)
        print('===keys===', keys)
        print('===breakdowns===', cartesian_product)
        for key, value in keys.items():
            for breakdown in cartesian_product:
                if frozenset(breakdown).issubset(key):
                    pos = product_index_sets.get(frozenset(breakdown))
                    if pos is not None:
                        aggregates[pos]['count'] += value

    for count in counts:
        count_params = []
        for field in fields_map.keys():
            if field == 'period':   
                field_val=None
            else:
                field_val = getattr(count, field)
            if field == 'subcategory':
                field_val = field_val.name 
            if field_val is not None:
                count_params.append(field_val)
        if split in ['month', 'quarter']:
            count_params.append(period_func(count.event.end))

        param_set = frozenset(count_params)
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


def social_aggregates(user, indicator, split, project, organization, start, end, platform=False):
    posts = get_posts_from_indicator(user, indicator, project, organization, start, end)
    aggregates = defaultdict(int)

    if split in ['month', 'quarter']:
        # Structure: { period: { platform: {metric: value} } }
        by_period = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        period_func = get_quarter_string if split == 'quarter' else get_month_string

        for post in posts:
            likes = post.likes or 0
            views = post.views or 0
            comments = post.comments or 0

            engagement = likes + views + comments

            period = period_func(post.published_at)
            post_platform = post.platform or 'unknown'

            by_period[period][post_platform]['likes'] += likes
            by_period[period][post_platform]['views'] += views
            by_period[period][post_platform]['comments'] += comments
            by_period[period][post_platform]['total_engagement'] += engagement

            aggregates['likes'] += likes
            aggregates['views'] += views
            aggregates['comments'] += comments
            aggregates['total_engagement'] += engagement

        # Convert nested defaultdicts to regular dicts
        aggregates['by_period'] = {
            period: {plat: dict(metrics) for plat, metrics in plat_data.items()}
            for period, plat_data in by_period.items()
        }
    else:
        by_platform = defaultdict(lambda: defaultdict(int))

        for post in posts:
            likes = post.likes or 0
            views = post.views or 0
            comments = post.comments or 0
            engagement = likes + views + comments
            post_platform = post.platform or 'unknown'

            by_platform[post_platform]['likes'] += likes
            by_platform[post_platform]['views'] += views
            by_platform[post_platform]['comments'] += comments
            by_platform[post_platform]['total_engagement'] += engagement

            aggregates['likes'] += likes
            aggregates['views'] += views
            aggregates['comments'] += comments
            aggregates['total_engagement'] += engagement

        aggregates['by_platform'] = {plat: dict(metrics) for plat, metrics in by_platform.items()}

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
        
def get_achievement(user, target):
    '''
    Slightly lighter weight helper that ignores demographics and just gets the raw totals for comparisons against
    targets.

    Note that we cascade all of these so that child organizations achievement is included when viewing parents.
    '''
    task = target.task
    start = target.start
    end = target.end
    indicator = task.indicator

    total = 0
    #respondent and count both use event counts
    if indicator.indicator_type in [Indicator.IndicatorType.RESPONDENT, Indicator.IndicatorType.COUNT]:
        valid_counts  = get_event_counts_from_indicator(
            user=user,
            indicator=indicator, 
            project=task.project,
            start=start,
            end=end, 
            cascade=True,
            params={},
            organization=task.organization,
            filters=None
        )
        total += sum(count.count or 0 for count in valid_counts)
        #respondent also pulls interactions
        if indicator.indicator_type == Indicator.IndicatorType.RESPONDENT:
            valid_irs = get_interactions_from_indicator(
                user=user,
                indicator=indicator,
                project=task.project,
                start=start,
                end=end,
                cascade=True,
                organization=task.organization,
                filters=None
            )
            if indicator.require_numeric:
                if indicator.subcategories.exists():
                    # Prefetch all subcategories once
                    subcats = get_interaction_subcats(valid_irs)
                    # Filter for relevant interactions only
                    subcats = subcats.filter(interaction__in=valid_irs)
                    total += sum(cat.numeric_component or 0 for cat in subcats)
                else:
                    total += sum(ir.numeric_component or 0 for ir in valid_irs)
            else:
                total += valid_irs.count()
    #pull event numbers for raw event count/org count tests
    elif indicator.indicator_type in [Indicator.IndicatorType.EVENT_NO, Indicator.IndicatorType.ORG_EVENT_NO]:
        valid_events = get_events_from_indicator(
            user=user,
            indicator=indicator,
            organization=task.organization,
            project=task.project,
            start=start,
            end=end, 
            cascade=True,
        )
        if indicator.indicator_type == Indicator.IndicatorType.EVENT_NO:
            total += len(valid_events)
        elif indicator.indicator_type == Indicator.IndicatorType.ORG_EVENT_NO:
            total += sum(e.organizations.count() for e in valid_events)
    #pull posts for social. Using total engagement for now
    elif indicator.indicator_type == Indicator.IndicatorType.SOCIAL:
        valid_posts = get_posts_from_indicator(
            user=user,
            indicator=indicator,
            project=task.project,
            organization=task.organization,
            start=start,
            end=end, 
            cascade=True,
            filters=None,
        )
        total += sum(((p.likes or 0) + (p.comments or 0) + (p.views or 0)) for p in valid_posts)
    return total



