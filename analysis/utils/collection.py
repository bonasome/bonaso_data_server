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



# dict that converts a couple of names as they appear in filters to how the django respondent model will expect them
FILTERS_MAP = {
    'kp_type': 'kp_status__name',
    'disability_type': 'disability_status__name',
}

def get_interactions_from_indicator(user, indicator, project=None, organization=None, start=None, end=None, filters=None, cascade=False):
    '''
    Helper function get queryset of interactions that match a set of conditions. Returns a queryset of 
    interactions that match the provided args.
    - user (user instance): The user making the request, for managing perms
    - indicator (indicator instance): The indicator these interactions should be related to 
    - project (project instance, optional): The project this data should be scoped to
    - organization (organization instance, optional): The organization this data should be scoped to
    - start (ISO date string, optional): Start collecting data recorded after this date
    - end (ISO date string, optional): Only collect data recorded before this date
    - filters (object, optional): A list of model field filters to apply to this queryset
    - cascade (boolean, optional): If scoped to an organization and project, should this include the organization's 
        child organizations as well
    '''
    #default queryset is everything related to the indicator
    queryset = Interaction.objects.filter(task__indicator=indicator)
    
    #filter based on perms
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
    # project param
    if project:
        queryset=queryset.filter(task__project=project)
    
    if organization:
        #if cascade is true and there is a project, get a list of child orgs for the project and include those as well
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
        #otherwise only include the organization
        else:
            queryset=queryset.filter(task__organization=organization)

    #date scoping
    if start:
        queryset=queryset.filter(interaction_date__gte=start)
    if end:
        queryset=queryset.filter(interaction_date__lte=end)

    #sort out filters
    if filters:
        for field, values in filters.items():
            if field == 'subcategory':
                continue # this has to be handled at a lower level, during aggregations
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
                if len(values) == 2 or len(values) == 0: #if either no values exist or both are selected, return all
                    continue
                if values[0] == 'citizen': #simple bool check since we store citizenship as a string
                    queryset = queryset.filter(respondent__citizenship='BW') #compare to two digit code for Botswana
                elif values[0] == 'non_citizen':
                    queryset = queryset.exclude(respondent__citizenship='BW')
            else:
                field_name = FILTERS_MAP.get(field, field)
                if isinstance(values, list): #if its a list, check if it includes
                    lookup = f"respondent__{field_name}__in"
                    queryset = queryset.filter(**{lookup: values})
                else:
                    queryset = queryset.filter(**{field_name: values}) #otherwise run a straight filter
    # filter out any flagged interactions or interactions that belong to flagged respondents
    queryset = queryset.exclude(flags__resolved=False).exclude(respondent__flags__resolved=False).distinct()

    return queryset

def get_interaction_subcats(interactions, filter_ids=None):
    '''
    Small helper to prefetch valid subcats. Returns queryset of InteractionSubcategory instances
    - interactions (queryset): queryset of interactions to get subcategories for
    - filter_ids (list, optional): list of indicator subcategory ids to include
    '''
    interaction_ids = [ir.id for ir in interactions]
    
    #if filter ids are provided, check if the id is in the list
    if filter_ids:
        filter_ids = [int(fid) for fid in filter_ids]
        return InteractionSubcategory.objects.filter(interaction__id__in=interaction_ids, subcategory_id__in=filter_ids)
    return InteractionSubcategory.objects.filter(interaction__id__in=interaction_ids) #otherwise return all objects from the interactions

def get_event_counts_from_indicator(user, indicator, params, project=None, organization=None, start=None, end=None, filters=None, cascade=False):
    '''
    Helper function get queryset of Demographic count that match a set of conditions. Returns queryset of
    DemographicCount instances.
    - user (user instance): The user making the request, for managing perms
    - indicator (indicator instance): The indicator these interactions should be related to 
    - params (object, optional): List of fields to split the data by
    - project (project instance, optional): The project this data should be scoped to
    - organization (organization instance, optional): The organization this data should be scoped to
    - start (ISO date string, optional): Start collecting data recorded after this date
    - end (ISO date string, optional): Only collect data recorded before this date
    - filters (object, optional): A list of model field filters to apply to this queryset
    - cascade (boolean, optional): If scoped to an organization and project, should this include the organization's 
        child organizations as well
    '''

    #default by fetching all counts whose task's indicator match the provided indicator
    queryset = DemographicCount.objects.filter(task__indicator=indicator)

    # filter out any counts that do not have the params requested by the user
    if params:
        query = Q()
        for field, should_exist in params.items():
            if should_exist:
                query |= Q(**{f"{field}__isnull": True})
        queryset = queryset.filter(query)

    #filter queryset based on the user's permissions
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

    #scope queryset to provided arguments   
    if project:
        queryset=queryset.filter(task__project=project)
    if organization:
        #if organization, cascade, and project are provided, include both the provided organization and its child orgs in the query
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
    #scope to dates
    if start:
        queryset=queryset.filter(event__start__gte=start)
    if end:
        queryset=queryset.filter(event__end__lte=end)

    #filter based on model filter fields 
    if filters:
        for field, values in filters.items():
            if isinstance(values, list):
                lookup = f"{field}__in"
                queryset = queryset.filter(**{lookup: values})
            else:
                queryset = queryset.filter(**{field: values})

    #exclude flagged objects
    queryset = queryset.exclude(flags__resolved=False).distinct()
    return queryset

def get_events_from_indicator(user, indicator, project=None, organization=None, start=None, end=None, cascade=False):
    '''
    Helper function get queryset of interactions that match a set of conditions. Returns queryset of Event instances.
    - user (user instance): The user making the request, for managing perms
    - indicator (indicator instance): The indicator these interactions should be related to 
    - project (project instance, optional): The project this data should be scoped to
    - organization (organization instance, optional): The organization this data should be scoped to
    - start (ISO date string, optional): Start collecting data recorded after this date
    - end (ISO date string, optional): Only collect data recorded before this date
    - cascade (boolean, optional): If scoped to an organization and project, should this include the organization's 
        child organizations as well
    '''
    #default to fetching queryset of all events that are realted to a task that has the requested indicator and that is marked as complete
    queryset = Event.objects.filter(tasks__indicator=indicator, status=Event.EventStatus.COMPLETED)
    
    #check permissions
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
    #filter by project
    if project:
        queryset=queryset.filter(tasks__project=project)
    #filter by organization, using the organization associated with the task
    if organization:
        #if organization, project, and cascade, fetch both the requested organization and its child organizations for that project
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
        #if not cascade, just fetch the org
        else:
            queryset=queryset.filter(tasks__organization=organization)
    # date filters
    if start:
        queryset=queryset.filter(start__gte=start)
    if end:
        queryset=queryset.filter(end__lte=end)

    return queryset.distinct()

def get_posts_from_indicator(user, indicator, project, organization, start, end, filters=None, cascade=False):
    '''
    Helper function get queryset of interactions that match a set of conditions. Returns queryset of SocialMediaPost instances. 
    - user (user instance): The user making the request, for managing perms
    - indicator (indicator instance): The indicator these interactions should be related to 
    - project (project instance, optional): The project this data should be scoped to
    - organization (organization instance, optional): The organization this data should be scoped to
    - start (ISO date string, optional): Start collecting data recorded after this date
    - end (ISO date string, optional): Only collect data recorded before this date
    - filters (object, optional): Filters to include (only accepts platform currently)
    - cascade (boolean, optional): If scoped to an organization and project, should this include the organization's 
        child organizations as well
    '''
    #default by getting all posts linked to a task that has the requested indicator
    queryset = SocialMediaPost.objects.filter(tasks__indicator=indicator)

    #permissionc checks
    if user.role == 'admin':
        queryset=queryset
    elif user.role == 'client':
        #this is an edge case, but make sure if a post linked to two projects, it doesn't accidently
        #pull one that shoudn't be there
        queryset=queryset.filter(tasks__project__client=user.client_organization, tasks__indicator=indicator,)
    else:
        child_orgs = ProjectOrganization.objects.filter(
                parent_organization=user.organization,
            ).values_list('organization', flat=True)
        queryset = queryset.filter(
                Q(tasks__organization=user.organization) | Q(tasks__organization__in=child_orgs)
            )
    
    #project filter
    if project:
        queryset=queryset.filter(tasks__project=project)
    # organization filter
    if organization:
         #if organization, project, and cascade, fetch both the requested organization and its child organizations for that project
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
        # otherwise just fetch the organization
        else:
            queryset=queryset.filter(tasks__organization=organization)
    #date filters
    if start:
        queryset=queryset.filter(published_at__gte=start)
    if end:
        queryset=queryset.filter(published_at__lte=end)
    # sort through filters object with model filters and apply them (only accepts platform)
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
    Helper to pull related pregnancy objects a build a map for easy checks. Returns a dict with respondent ids as
    the key and a list of pregnancy instances as the item. 
    - respondent_ids (list): list of ids to fetch related pregnancies for.
    '''
    pregnancies = Pregnancy.objects.filter(respondent_id__in=respondent_ids)

    pregnancies_by_respondent = {}
    for p in pregnancies:
        if p and p.term_began:
            pregnancies_by_respondent.setdefault(p.respondent_id, []).append(p)
    return pregnancies_by_respondent

def get_hiv_statuses(respondent_ids):
    '''
    Helper to pull related HIV status and build a map. Returns a dict with respondent ids as they key and a
    list of HIVStatus instances as the item. 
    '''
    hiv_statuses = HIVStatus.objects.filter(respondent_id__in=respondent_ids)
    hiv_status_by_respondent = {}
    for hs in hiv_statuses:
        if hs and hs.date_positive:
            hiv_status_by_respondent.setdefault(hs.respondent_id, []).append(hs)
    return hiv_status_by_respondent
