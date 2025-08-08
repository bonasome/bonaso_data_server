from django.db.models import Q, Count
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

def demographic_aggregates(user, indicator, params, split=None, project=None, organization=None, start=None, end=None, filters=None, repeat_only=False, n=2, cascade=False):
    #get a list of interactions prefiltered based on user role/filters
    interactions = get_interactions_from_indicator(user, indicator, project, organization, start, end, filters, cascade)
    if repeat_only:
        #NOTE: This track respondents that have had the interaction repeatedly (i.e., the number of respondents reached with NCD messages at least three times or number of respondents who have received condoms more than once)
        #Selecting this will ignore any numeric component to the interaction and just raw count unique respondents
        interactions = get_repeats(interactions, n)
    counts=[] #default counts to empty list
    if not repeat_only: #only collect counts if repear is disabled
        #get list of prefiltered counts
        counts = get_event_counts_from_indicator(user, indicator, params, project, organization, start, end, filters, cascade)
    #build a map  of all requested fields that need to be aggregated by
    fields_map = {}
    include_subcats=False
    for param, include in params.items():
        if include:
            #get list of subcats from indicator
            if param == 'subcategory' and indicator.subcategories.exists():
                include_subcats = True
                fields_map['subcategory'] = [cat.name for cat in indicator.subcategories.all()]
                continue
            elif param == 'subcategory':
                print('WARNING: This indicator has no subcategories.')
                continue
            #this model contains all supported demographic fields, pull the list of options from it
            field = DemographicCount._meta.get_field(param)
            if field:
                fields_map[param] = [value for value, label in field.choices]
      
    #if time split is required, add an additional 'field' deonting the time period
    if split in ['month', 'quarter']:
        period_func = get_quarter_string if split == 'quarter' else get_month_string
        periods = set(sorted({period_func(i.interaction_date) for i in interactions}) + sorted({period_func(count.event.end) for count in counts}))
        fields_map['period'] = periods
    #fields_map = {age_range: [18-24, 25-34...], sex: ['Male', 'Female]}

    #create a cartsial product of all possible combos
    cartesian_product = list(product(*[bd for bd in fields_map.values()]))
    #[(18-24, M), (18-24, F)]

    #use an index based key system to track this
    product_index = {tuple(p): i for i, p in enumerate(cartesian_product)}
    
    #prepare the aggregates dict
    aggregates = {}
    for pos, arr in enumerate(cartesian_product):
        aggregates[pos] = {} #use the index as a key
        for i, field in enumerate(fields_map.keys()):
            aggregates[pos][field] = arr[i]
        aggregates[pos]['count'] = 0 #set default count to 0
    #{1: {age_range: 18-24, sex: M}, 2: {age_range: 18-24, sex: F}}

    #prefetch related information for breakdowns
    respondent_ids = {i.respondent_id for i in interactions}
    hiv_status_map = get_hiv_statuses(respondent_ids=respondent_ids)
    pregnancies_map = get_pregnancies(respondent_ids=respondent_ids)

    #also look fetch related subcategories now if required
    subcat_filter = None
    if filters:
        subcat_filter = filters.get('subcategory', None)

    subcats = get_interaction_subcats(interactions, subcat_filter)

    product_index_sets = {frozenset(k): v for k, v in product_index.items()}

    seen_respondents = set()
    #loop through each interaction and add the appropriate value
    for interaction in interactions:
        keys = build_keys(interaction, pregnancies_map, hiv_status_map, subcats, include_subcats)
        for key, value in keys.items():
            for breakdown in cartesian_product:
                if frozenset(breakdown).issubset(frozenset(key)):
                    pos = product_index_sets.get(frozenset(breakdown))
                    if pos is not None:
                        #add the value (1 default, else depends on numeric inputs, unless repeat only is enabled, in which case just add 1 unless the respondent has already been seen)
                        if not repeat_only:
                            aggregates[pos]['count'] += value
                        else:
                            if interaction.respondent_id not in seen_respondents:
                                aggregates[pos]['count'] += 1
                                seen_respondents.add(interaction.respondent_id)
    if counts: #only perform this if counts are available (and not expressly disabled by the repeat_only arg)
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

def get_repeats(interactions, n):
    repeat_respondents = list(
        interactions
            .values('respondent')
            .annotate(total=Count('id'))
            .filter(total__gte=n)
            .values_list('respondent', flat=True)
    )
    repeat_only = interactions.filter(respondent_id__in=repeat_respondents)
    return repeat_only

def event_no_aggregates(user, indicator, split, project, organization, start, end, cascade):
    events = get_events_from_indicator(user, indicator, project, organization, start, end, cascade)
    aggregates = defaultdict(int)
    fields_map = {}
    if split in ['month', 'quarter']:
        period_func = get_quarter_string if split == 'quarter' else get_month_string
        fields_map['period'] = list({period_func(e.end) for e in events})

    cartesian_keys = list(fields_map.keys())
    cartesian_product = list(product(*fields_map.values()))
    product_index = {tuple(comb): i for i, comb in enumerate(cartesian_product)}

    aggregates = {}
    for i, comb in enumerate(cartesian_product):
        aggregates[i] = dict(zip(cartesian_keys, comb))
        aggregates[i]['count'] = 0

    for event in events:
        key = []
        if split:
            period = period_func(event.end) if split else None
            key.append(period)

        key_tuple = tuple(key)
        pos = product_index.get(key_tuple)
        if pos is not None:

            aggregates[pos]['count'] += 1

    return dict(aggregates)

def event_org_no_aggregates(user, indicator, split, project, organization, start, end, cascade):
    events = get_events_from_indicator(user, indicator, project, organization, start, end, cascade)
    aggregates = defaultdict(int)

    fields_map = {}
    if split in ['month', 'quarter']:
        period_func = get_quarter_string if split == 'quarter' else get_month_string
        fields_map['period'] = list({period_func(e.end) for e in events})

    cartesian_keys = list(fields_map.keys())
    cartesian_product = list(product(*fields_map.values()))
    product_index = {tuple(comb): i for i, comb in enumerate(cartesian_product)}

    aggregates = {}
    for i, comb in enumerate(cartesian_product):
        aggregates[i] = dict(zip(cartesian_keys, comb))
        aggregates[i]['count'] = 0

    for event in events:
        
        key = []
        if split:
            period = period_func(event.end) if split else None
            key.append(period)

        key_tuple = tuple(key)
        pos = product_index.get(key_tuple)
        if pos is not None:

            aggregates[pos]['count'] += event.organizations.count()

    return dict(aggregates)


def social_aggregates(user, indicator, params, split, project, organization, start, end, filters, cascade):
    posts = get_posts_from_indicator(user, indicator, project, organization, start, end, filters, cascade)
    aggregates = defaultdict(int)
    #structure: pos: {platform: fb, metric: comments, count: 7}
    include_platform = False
    include_metric = False
    metrics = ['comments', 'views', 'likes']
    fields_map = {}
    if split in ['month', 'quarter']:
        period_func = get_quarter_string if split == 'quarter' else get_month_string
        fields_map['period'] = list({period_func(p.published_at) for p in posts})
    for param, include in params.items():
        if param not in ['platform', 'metric']:
            continue #other params not supported
        if include:
            if param == 'platform':
                include_platform = True
                fields_map['platform'] = list({p.platform for p in posts})
            elif param == 'metric':
                include_metric = True
                fields_map['metric'] = metrics 

    

    cartesian_keys = list(fields_map.keys())
    cartesian_product = list(product(*fields_map.values()))
    product_index = {tuple(comb): i for i, comb in enumerate(cartesian_product)}

    aggregates = {}
    for i, comb in enumerate(cartesian_product):
        aggregates[i] = dict(zip(cartesian_keys, comb))
        aggregates[i]['count'] = 0

    for post in posts:
        period = period_func(post.published_at) if split else None
        for metric in metrics if include_metric else [None]:
            key = []
            if split:
                key.append(period)
            if include_platform:
                key.append(post.platform)
            if include_metric:
                key.append(metric)

            key_tuple = tuple(key)
            pos = product_index.get(key_tuple)
            if pos is not None:
                count = getattr(post, metric) or 0 if include_metric else (post.comments + post.likes + post.views)
                aggregates[pos]['count'] += count

    return dict(aggregates)

def aggregates_switchboard(user, indicator, params, split=None, project=None, organization=None, start=None, end=None, filters=None, repeat_only=False, n=2, cascade=False):
    aggregates = {}
    if indicator.indicator_type == 'respondent':
        aggregates = demographic_aggregates(user, indicator, params, split, project, organization, start, end, filters, repeat_only, n, cascade)
    if indicator.indicator_type == 'event_no':
        aggregates = event_no_aggregates(user, indicator, split, project, organization, start, end, cascade)
    if indicator.indicator_type == 'org_event_no':
        aggregates = event_org_no_aggregates(user, indicator, split, project, organization, start, end, cascade)
    if indicator.indicator_type == 'social':
        aggregates = social_aggregates(user, indicator, params, split, project, organization, start, end, filters, cascade)
    return aggregates

