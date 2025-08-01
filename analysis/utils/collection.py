from django.db.models import Q
from respondents.models import Interaction, HIVStatus, Pregnancy, InteractionSubcategory
from projects.models import ProjectOrganization
from events.models import DemographicCount, Event
from datetime import date
from social.models import SocialMediaPost

'''
This is a set of helpers that prefetches models based on perms/filters/time period so that the aggregators
can focus on aggregating.
'''



#similar thing for filters, but get the name
FILTERS_MAP = {
    'kp_type': 'kp_status__name',
    'disability_type': 'disability_status__name',
    # others as needed
}

def get_interactions_from_indicator(user, indicator, project=None, organization=None, start=None, end=None, filters=None, cascade=False):
    '''
    Helper function get get list of interactions that match a set of conditions.

    CASCADE: Determines if this should pull the organization and its child org, only works if a project is provided.
    '''
    queryset = Interaction.objects.filter(task__indicator=indicator)
    
    #start with perms
    if user.role == 'admin':
        queryset=queryset
    elif user.role == 'client':
        queryset=queryset.filter(task__project__client=user.client_organization)
    elif user.role in ['meofficer', 'manager']:
        # Find all orgs user has access to (own + child)
        accessible_orgs = list(
            ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)
        )
        accessible_orgs.append(user.organization.id)
        
        queryset = queryset.filter(
            task__organization__in=accessible_orgs
        )
    #handle additional parameters
    if project:
        queryset=queryset.filter(task__project=project)
    
    if organization:
        if cascade and project:
            accessible_orgs = list(
                ProjectOrganization.objects.filter(
                    parent_organization=organization, project=project
                ).values_list('organization', flat=True)
            )
            accessible_orgs.append(organization.id)
            
            queryset = queryset.filter(
                task__organization__in=accessible_orgs
            )
        else:
            queryset=queryset.filter(task__organization=organization)

    if start:
        queryset=queryset.filter(interaction_date__gte=start)
    if end:
        queryset=queryset.filter(interaction_date__lte=end)

    #sort out filters
    if filters:
        for field, values in filters.items():
            if field == 'subcategory':
                continue #this has to be handled at a lower level
            elif field in ['pregnancy', 'hiv_status']:
                if len(values) == 2 or len(values) == 0: #if either no values exist or both are selected, return all
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
                    if values[0] == 'pregnant':
                        queryset = queryset.filter(id__in=preg_ids)
                    elif values[0] == 'not_pregnant':
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
                    if values[0] == 'hiv_positive':
                        queryset = queryset.filter(id__in=pos_ids)
                    elif values[0] == 'hiv_negative':
                        queryset = queryset.exclude(id__in=pos_ids)
            elif field == 'citizenship':
                if len(values) == 2 or len(values) == 0:
                    continue
                if values[0] == 'citizen': #simple bool check since we store citizenship as a string
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
    queryset = queryset.exclude(flags__resolved=False).exclude(respondent__flags__resolved=False).distinct()

    return queryset

def get_interaction_subcats(interactions, filter_ids=None):
    '''
    Small helper to prefetch valid subcats.
    '''
    interaction_ids = [ir.id for ir in interactions]
    if filter_ids:
        return InteractionSubcategory.objects.filter(interaction__id__in=interaction_ids).exclude(id__in=filter_ids)
    return InteractionSubcategory.objects.filter(interaction__id__in=interaction_ids)

def get_event_counts_from_indicator(user, indicator, params, project, organization, start, end, filters, cascade=False):
    '''
    Similar helper function get mathcing counts from events. Takes params only to prefilter any counts
    that do not match the demographic values.

    CASCADE: Determines if this should pull the organization and its child org, only works if a project is provided.
    '''
    query = Q()
    for field, should_exist in params.items():
        if should_exist:
            query |= Q(**{f"{field}__isnull": True})

    queryset = DemographicCount.objects.filter(task__indicator=indicator)
    if user.role == 'admin':
        queryset=queryset
    elif user.role == 'client':
        queryset=queryset.filter(task__project__client=user.client_organization)
    else:
        child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
        queryset = queryset.filter(
                Q(task__organization=user.organization) | Q(task__organization__in=child_orgs)
            )
        
    if project:
        queryset=queryset.filter(task__project=project)
    if organization:
        if cascade and project:
            accessible_orgs = list(
                ProjectOrganization.objects.filter(
                    parent_organization=organization, project=project
                ).values_list('organization', flat=True)
            )
            accessible_orgs.append(organization.id)
            
            queryset = queryset.filter(
                task__organization__in=accessible_orgs
            )
        else:
            queryset=queryset.filter(task__organization=organization)
    if start:
        queryset=queryset.filter(event__start__gte=start)
    if end:
        queryset=queryset.filter(event__end__lte=end)
    if user.role not in ['admin', 'client']:
        child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
        queryset = queryset.filter(
                Q(task__organization=user.organization) | Q(task__organization__in=child_orgs)
            )
        
    if filters:
        for field, values in filters.items():
            if isinstance(values, list):
                lookup = f"{field}__in"
                queryset = queryset.filter(**{lookup: values})
            else:
                queryset = queryset.filter(**{field: values})

    queryset = queryset.exclude(flags__resolved=False).distinct()
    return queryset

def get_events_from_indicator(user, indicator, project, organization, start, end, cascade=False):
    '''
    Function that pulls events that match conditions (for event count/org count indicator types).
    Does not accept filters, because why?

    CASCADE: Determines if this should pull the organization and its child org, only works if a project is provided.
    '''
    queryset = Event.objects.filter(tasks__indicator=indicator, status=Event.EventStatus.COMPLETED)
    if user.role == 'admin':
        queryset=queryset
    elif user.role == 'client':
        queryset=queryset.filter(tasks__indicator=indicator, tasks__project__client=user.client_organization)
    else:
        child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
        queryset = queryset.filter(
                Q(tasks__organization=user.organization) | Q(tasks__organization__in=child_orgs)
            )
    if project:
        queryset=queryset.filter(tasks__project=project)
    if organization:
        if cascade and project:
            accessible_orgs = list(
                ProjectOrganization.objects.filter(
                    parent_organization=organization, project=project
                ).values_list('organization', flat=True)
            )
            accessible_orgs.append(organization.id)
            
            queryset = queryset.filter(
                tasks__organization__in=accessible_orgs
            )
        else:
            queryset=queryset.filter(tasks__organization=organization)
    if start:
        queryset=queryset.filter(start__gte=start)
    if end:
        queryset=queryset.filter(end__lte=end)

    return queryset.distinct()

#platform is the only filter social posts can accept
def get_posts_from_indicator(user, indicator, project, organization, start, end, filters=None, cascade=False):
    '''
    Function that pulls social posts that match conditions. Takes platform as a possible filter.

    CASCADE: Determines if this should pull the organization and its child org, only works if a project is provided.
    '''
    queryset = SocialMediaPost.objects.filter(tasks__indicator=indicator)
    if user.role == 'admin':
        queryset=queryset
    elif user.role == 'client':
        #this is an edge case, but make sure if an event is linked to two projects, it doesn't accidently
        #pull one that shoudn't be there
        queryset=queryset.filter(tasks__project__client=user.client_organization, tasks__indicator=indicator,)
    else:
        child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
        queryset = queryset.filter(
                Q(tasks__organization=user.organization) | Q(tasks__organization__in=child_orgs)
            )
    if project:
        queryset=queryset.filter(tasks__project=project)
    if organization:
        if cascade and project:
            accessible_orgs = list(
                ProjectOrganization.objects.filter(
                    parent_organization=organization, project=project
                ).values_list('organization', flat=True)
            )
            accessible_orgs.append(organization.id)
            
            queryset = queryset.filter(
                tasks__organization__in=accessible_orgs
            )
        else:
            queryset=queryset.filter(tasks__organization=organization)
    if start:
        queryset=queryset.filter(published_at__gte=start)
    if end:
        queryset=queryset.filter(published_at__lte=end)
    if filters:
        for field, values in filters.items():
            if isinstance(values, list):
                lookup = f"{field}__in"
                queryset = queryset.filter(**{lookup: values})
            else:
                queryset = queryset.filter(**{field: values})
    queryset = queryset.exclude(flags__resolved=False).distinct()
    return queryset

def get_pregnancies(respondent_ids):
    '''
    Helper to pull related pregnancy objects a build a map for easy checks. 
    '''
    pregnancies = Pregnancy.objects.filter(respondent_id__in=respondent_ids)

    pregnancies_by_respondent = {}
    for p in pregnancies:
        if p and p.term_began:
            pregnancies_by_respondent.setdefault(p.respondent_id, []).append(p)
    return pregnancies_by_respondent

def get_hiv_statuses(respondent_ids):
    '''
    Helper to pull related HIV status and build a map.
    '''
    hiv_statuses = HIVStatus.objects.filter(respondent_id__in=respondent_ids)
    hiv_status_by_respondent = {}
    for hs in hiv_statuses:
        if hs and hs.date_positive:
            hiv_status_by_respondent.setdefault(hs.respondent_id, []).append(hs)
    return hiv_status_by_respondent
