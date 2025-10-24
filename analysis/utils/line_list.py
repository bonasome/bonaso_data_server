from datetime import date
from respondents.models import Response
from indicators.models import Indicator
from projects.models import ProjectOrganization
from analysis.utils.aggregates import get_hiv_statuses, get_pregnancies
def prep_line_list(user, start=None, end=None, assessment=None, project=None, organization=None, cascade=False):
    '''
    Collect a list of responses and return them as an array of set rows for a line list
    - user (user instance): used to check permissions
    - start (ISO date string, optional): only collect responses after this date
    - end (ISO date string, optional): only collect responses before this date
    - assessment (assessment instance, optional): only collect responses whose interaction's task is realted to this assessment
    - project (project instance, optional): only collect responses whose interaction's task is related to this project
    - organization (organization instance, optional): only collect responses whose interaction's task is related to this org
    - cascade (boolean, optional): if project and organization are provided, also collect responses from child organizations
    '''
    queryset= Response.objects.all()
    
    #start with perms
    if user.role == 'admin':
        queryset=queryset
    elif user.role == 'client':
        queryset=queryset.filter(interaction__task__project__client=user.client_organization)
    elif user.role in ['meofficer', 'manager']:
        # Find all orgs user has access to (own + child)
        accessible_orgs = list(
            ProjectOrganization.objects.filter(
                parent_organization=user.organization
            ).values_list('organization', flat=True)
        )
        accessible_orgs.append(user.organization.id)
        
        queryset = queryset.filter(
            interaction__task__organization__in=accessible_orgs
        )
    else:
        queryset = queryset.filter(created_by=user)
    # filter by assessment if requested
    if assessment:
        queryset = queryset.filter(interaction__task__assessment=assessment)
    #handle additional parameters
    if project:
        queryset=queryset.filter(interaction__task__project=project)
    
    if organization:
        # if project, organization, and cascade, also fetch data from any child orgs
        if cascade and project:
            accessible_orgs = list(
                ProjectOrganization.objects.filter(
                    parent_organization=organization, project=project
                ).values_list('organization', flat=True)
            )
            accessible_orgs.append(organization.id)
            
            queryset = queryset.filter(
                interaction__task__organization__in=accessible_orgs
            )
        else:
            queryset=queryset.filter(interaction__task__organization=organization)
    #time filters
    if start:
        queryset=queryset.filter(response_date__gte=start)
    if end:
        queryset=queryset.filter(response_date__lte=end)
    
    respondent_ids = {r.interaction.respondent_id for r in queryset}
    hiv_status_map = get_hiv_statuses(respondent_ids=respondent_ids)
    pregnancies_map = get_pregnancies(respondent_ids=respondent_ids)

    rows = [] #stores the line list items
    #loop through each responses and build a row object
    for i, r in enumerate(queryset):
        value = None
        if r.indicator.type in [Indicator.Type.MULTI, Indicator.Type.SINGLE]:
            value = r.response_option.name if r.response_option else None
        if r.indicator.type in [Indicator.Type.BOOL]:
            value = r.response_boolean
        else:
            value = r.response_value 
        respondent = r.interaction.respondent
        row = {
            'index': i+1,
            'is_anonymous': respondent.is_anonymous,
            'first_name': respondent.first_name,
            'last_name': respondent.last_name,
            'id': respondent.id,
            'ward': respondent.ward,
            'village': respondent.village,
            'district': respondent.district,
            'sex': respondent.sex,
            'dob': respondent.dob,
            'age_range' : respondent.age_range,
            'citizenship': respondent.citizenship,
            'email': respondent.email,
            'phone_number': respondent.phone_number,
            'comments': respondent.comments,
            'kp_status': [kp.name for kp in respondent.kp_status.all()],
            'disability_status': [d.name for d in respondent.disability_status.all()],
            'indicator': str(r.indicator),
            'response_date': r.response_date,
            'response_location': r.response_location,
            'organization': str(r.interaction.task.organization),
            'project': str(r.interaction.task.project),
            'value': value,
            'flagged': (r.interaction.flags.filter(resolved=False).count() > 0 or respondent.flags.filter(resolved=False).count() > 0)
        }
        hiv_status_list = hiv_status_map.get(respondent.id, [])
        row['hiv_status'] = any(hs.date_positive <= r.response_date for hs in hiv_status_list)

        preg_list = pregnancies_map.get(respondent.id, [])
        row['pregnant'] = any(p.term_began <= r.response_date <= (p.term_ended or date.today()) for p in preg_list)
        rows.append(row)
    return rows