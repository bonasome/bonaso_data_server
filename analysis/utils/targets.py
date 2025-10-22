from django.db.models import Q
from projects.models import Target, ProjectOrganization
from datetime import date
from collections import defaultdict
from indicators.models import Indicator
from analysis.utils.collection import get_counts_from_indicator, get_interactions_from_indicator, get_events_from_indicator, get_posts_from_indicator
from analysis.utils.periods import get_month_strings_between, get_quarter_strings_between

def get_target_aggregates(user, indicator, split, start=None, end=None, project=None, organization=None):
    '''
    
    '''
    queryset = Target.objects.filter(indicator=indicator)

    if user.role not in ['admin', 'client']:
        child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
        queryset = queryset.filter(
                Q(organization=user.organization) | Q(organization__in=child_orgs)
            )

    if project:
        queryset = queryset.filter(project=project)
    if organization:
        queryset = queryset.filter(organization=organization)
    if start:
        queryset = queryset.filter(start__gte=start)
    if end:
        queryset = queryset.filter(end__lte=end)

    targets_map = defaultdict(float)

    range_func = get_quarter_strings_between if split == 'quarter' else get_month_strings_between

    for target in queryset:
        amount = target.amount
        if not amount and target.related_to and target.percentage_of_related:
            get_achievement(user, target, target.related_to)

        if not amount or not target.start or not target.end:
            continue

        periods = range_func(target.start, target.end)
        for period in periods:
            targets_map[period] += round(amount / len(periods))

    return dict(targets_map)
        
def get_achievement(user, target, related=None):
    '''
    Slightly lighter weight helper that ignores demographics and just gets the raw totals for comparisons against
    targets. Note that when collecting targets, data for child organizations is automatically included.

    - user (user instance): for checking permissions
    - target (target instance): target to collect information about
    - related (task instance): if this target is measured as the percentage of another task's achievement,
        pass that task here to get its achievement over the target's time period
    '''
    start = target.start
    end = target.end
    indicator = related if related else target.indicator # if this is getting achievement for a related task, use related, else use this target's task

    total = 0

    #if indicator is of the respondent type
    if indicator.category in [Indicator.Category.ASS]:
        #start by fetching related event counts
        valid_counts  = get_counts_from_indicator(
            user=user,
            indicator=indicator, 
            project=target.project,
            start=start,
            end=end, 
            cascade=True,
            params={},
            organization=target.organization,
            filters=None
        )
        total += sum(count.value or 0 for count in valid_counts)

        #get related interactions
        valid_responses = get_interactions_from_indicator(
            user=user,
            indicator=indicator,
            project=target.project,
            start=start,
            end=end,
            cascade=True,
            organization=target.organization,
            filters=None
        )
        valid_responses = valid_responses.order_by('interaction_id').distinct('interaction_id')
        # add the correct amount to the total, either by numeric component or just the raw count
        if indicator.type == Indicator.Type.INT:
            total += sum(r.response_value or 0 for r in valid_responses)
        else:
            total += valid_responses.count()

    elif indicator.category  in [Indicator.Category.MISC]:
        #start by fetching related event counts
        valid_counts  = get_counts_from_indicator(
            user=user,
            indicator=indicator, 
            project=target.project,
            start=start,
            end=end, 
            cascade=True,
            params={},
            organization=target.organization,
            filters=None
        )
        total += sum(count.value or 0 for count in valid_counts)

    # if event numer or org event number, fetch related events
    elif indicator.category in [Indicator.Category.EVENTS, Indicator.Category.ORGS]:
        valid_events = get_events_from_indicator(
            user=user,
            indicator=indicator,
            organization=target.organization,
            project=target.project,
            start=start,
            end=end, 
            cascade=True,
        )
        # if event no, add the count of events
        if indicator.category == Indicator.Category.EVENTS:
            total += len(valid_events)
        # if org number, add number of participants
        elif indicator.category == Indicator.Category.ORGS:
            total += sum(e.organizations.count() for e in valid_events)
    
    #pull posts for social. Using total engagement for now (though we should probably rethink this)
    elif indicator.category == Indicator.Category.SOCIAL:
        valid_posts = get_posts_from_indicator(
            user=user,
            indicator=indicator,
            project=target.project,
            organization=target.organization,
            start=start,
            end=end, 
            cascade=True,
            filters=None,
        )
        total += sum(((p.likes or 0) + (p.comments or 0) + (p.reach or 0) + (p.views or 0)) for p in valid_posts)
    return total



