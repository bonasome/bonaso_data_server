from django.db.models import Q
from projects.models import Target, ProjectOrganization
from datetime import date
from collections import defaultdict
from indicators.models import Indicator
from analysis.utils.collection import get_event_counts_from_indicator, get_interactions_from_indicator, get_interaction_subcats, get_events_from_indicator, get_posts_from_indicator
from analysis.utils.periods import get_month_strings_between, get_quarter_strings_between

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
    targets.

    Note that we cascade all of these so that child organizations achievement is included when viewing parents.
    '''
    task = related if related else target.task
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



