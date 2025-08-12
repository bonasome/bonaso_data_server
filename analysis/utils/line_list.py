from datetime import date
from respondents.models import Interaction
from projects.models import ProjectOrganization
from analysis.utils.aggregates import get_hiv_statuses, get_pregnancies, get_interaction_subcats
def prep_line_list(user, start=None, end=None, indicator=None, project=None, organization=None, cascade=None):
    '''
    Collect a list of interactions and return them as an array of set rows for a line list
    '''
    queryset= Interaction.objects.all()
    
    #start with perms
    if user.role == 'client':
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
    else:
        queryset = queryset.filter(created_by=user)

    if indicator:
        queryset = queryset.filter(task__indicator=indicator)
    #handle additional parameters
    if project:
        queryset=queryset.filter(task__project=project)
    
    if organization:
        #orgs relations are scoped by project, so only allow for cascading within the bounds of a specific project
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
    #time filters
    if start:
        queryset=queryset.filter(interaction_date__gte=start)
    if end:
        queryset=queryset.filter(interaction_date__lte=end)
    
    #prefetch related crap
    queryset = queryset.select_related(
        'respondent',
        'task',
        'task__indicator',
        'task__organization',
        'task__project',
    ).prefetch_related(
        'respondent__kp_status',
        'respondent__disability_status',
        'respondent__special_attribute',
    )
    
    subcategories = get_interaction_subcats(queryset)
    respondent_ids = {i.respondent_id for i in queryset}
    hiv_status_map = get_hiv_statuses(respondent_ids=respondent_ids)
    pregnancies_map = get_pregnancies(respondent_ids=respondent_ids)

    rows = [] #stores the line list items
    for i, ir in enumerate(queryset):
        respondent = ir.respondent
        row = {
            'index': i,
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
            'indicator': str(ir.task.indicator),
            'interaction_date': ir.interaction_date,
            'interaction_location': ir.interaction_location,
            'organization': str(ir.task.organization),
            'project': str(ir.task.project),
            'numeric_component': ir.numeric_component or None,
            'subcategory': None
        }
        hiv_status_list = hiv_status_map.get(ir.respondent.id, [])
        row['hiv_status'] = any(hs.date_positive <= ir.interaction_date for hs in hiv_status_list)

        preg_list = pregnancies_map.get(respondent.id, [])
        row['pregnant'] = any(p.term_began <= ir.interaction_date <= (p.term_ended or date.today()) for p in preg_list)
        #we'll treat each subcat is its own row
        subcats = subcategories.filter(interaction=ir)
        if subcats:
            for subcat in subcats:
                subset_row = row.copy()
                subset_row['subcategory'] = subcat.subcategory.name
                subset_row['numeric_component'] = subcat.numeric_component or None
                rows.append(subset_row)
        else:
            rows.append(row)
    return rows