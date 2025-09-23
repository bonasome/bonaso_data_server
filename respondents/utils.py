from django.utils.timezone import now
from datetime import date, datetime, timedelta
from django.db.models import Q
from respondents.models import Interaction, InteractionSubcategory, Respondent
from flags.utils import create_flag, resolve_flag
from projects.models import ProjectOrganization
from events.models import EventOrganization

#helper to manage potentially multiple flags created during id process
def _maybe_create_flag(flags_qs, respondent, reason, user):
    if not flags_qs.filter(reason=reason).exists():
        create_flag(respondent, reason, user, 'entry_error')

def respondent_flag_check(respondent, user):
    '''
    Auto create respondent flags realted to improperly configured Omang numbers for citizens.

    User is a required param since the user will be set as the caused_by property, which will determine
    who is alerted to the flag.
    - respondent(respondent instnace): the respondent object to check
    - user (user instance): the user making edits that may cause the flag
    '''
    flags = respondent.flags.filter(auto_flagged=True)
    id_no = str(respondent.id_no)

    # Rule 1: Length check (should be 9 digits)
    length_reason = 'ID Number (Omang) for Batswana must be 9 digits.'
    if len(id_no) != 9:
        _maybe_create_flag(flags, respondent, length_reason, user)
    else:
        resolve_flag(flags, length_reason)

    # Rule 2: Fifth digit must be '1' or '2'
    fifth_digit_reason = 'Invalid ID Number (Omang) (fifth digit must be a "1" or "2").'
    sex_reason = 'Fifth Digit of ID Number (Omang) does not match with respondent sex'
    if len(id_no) >= 5:
        fifth = id_no[4]
        if fifth not in ['1', '2']:
            _maybe_create_flag(flags, respondent, fifth_digit_reason, user)
        else:
            resolve_flag(flags, fifth_digit_reason)

        # Rule 3: Fifth digit must match declared sex
        if (respondent.sex == 'M' and fifth != '1') or (respondent.sex == 'F' and fifth != '2'):
            if respondent.sex == 'NB' or respondent.kp_status.filter(
                Q(name='TG') | Q(name='INTERSEX')
            ).exists():
                resolve_flag(flags, sex_reason)
            else:
                _maybe_create_flag(flags, respondent, sex_reason, user)
        else:
            resolve_flag(flags, sex_reason)
    else:
        # If ID is too short, mark both digit-based flags
        _maybe_create_flag(flags, respondent, fifth_digit_reason, user)
        _maybe_create_flag(flags, respondent, sex_reason, user)


def interaction_flag_check(interaction, user, downstream=False):
    '''
    Create flags for an interaction automatically for the following reason:
        -Multiple interactions over a 30 day period when not expressly allowed

    User is a required param since the user will be set as the caused_by property, which will determine
    who is alerted to the flag.

    Downstream lets the function know if this is a fully new update or if this is verifying dependent indicators.
    '''

    if not interaction.interaction_date or not interaction.task or not interaction.respondent:
        return
    
    outstanding_flags = interaction.flags.filter(auto_flagged=True)

    #Rule 1: Check if multiple interactions have occured within 30 days of each other
    date_value = None
    if isinstance(interaction.interaction_date, str):
        date_value = datetime.strptime(interaction.interaction_date, "%Y-%m-%d").date()
    elif isinstance(interaction.interaction_date, datetime):
        date_value = interaction.interaction_date.date()
    elif isinstance(interaction.interaction_date, date):
        date_value = interaction.interaction_date
    if not date_value:
        return
    
    past_thirty_days = date_value - timedelta(days=30)
    next_thirty_days = date_value + timedelta(days=30)
    last_year = date_value - timedelta(days=365)

    reason = (
        f'Respondent "{interaction.respondent}" has had an interaction associated '
        f'with task "{interaction.task.indicator.name}" within 30 days of this interaction.'
    )
    if not downstream and not interaction.task.indicator.allow_repeat:
        if Interaction.objects.filter(
            interaction_date__lte=next_thirty_days,
            interaction_date__gte=past_thirty_days,
            respondent=interaction.respondent, task__indicator=interaction.task.indicator
        ).exclude(pk=interaction.pk).exists():
            if not outstanding_flags.filter(reason=reason).exists():
                create_flag(interaction, reason, user, 'suspicious')
        else:
            resolve_flag(outstanding_flags, reason)
                
    #Rule 2: Check if the indicator requires a prerequsiite that does not exist
    prerequisites = interaction.task.indicator.prerequisites
    for prerequisite in prerequisites.all():
        if prerequisite:
            prereqs = Interaction.objects.filter(
                respondent=interaction.respondent,
                task__indicator=prerequisite,
                interaction_date__gte=last_year,
                interaction_date__lte=interaction.interaction_date,
            )
            reason = (
                    f'Indicator requires task "{prerequisite.name}" to have a valid interaction with this respondent within the past year. Make sure the prerequisite interaction is not in the future.'
                )
            if not prereqs.exists():
                if not outstanding_flags.filter(reason=reason).exists():
                    create_flag(interaction, reason, user, 'missing_prerequisite')
            else:
                resolve_flag(outstanding_flags, reason)

                #Rule 3: If match categories is enabled, the dependent interaction's subcategories must be a subset
                if interaction.task.indicator.match_subcategories_to == prerequisite:
                    most_recent = prereqs.order_by('-interaction_date').first()
                    reason = (f'The selected subcategories for task "{interaction.task.indicator.name}" do not match with the parent interaction associated with task "{most_recent.task.indicator.name}". This interaction will be flagged until the subcategories match.')
                    current_ids = set(
                        InteractionSubcategory.objects.filter(interaction=interaction)
                        .values_list("subcategory_id", flat=True)
                    )
                    previous_ids = set(most_recent.subcategories.values_list('id', flat=True))
                    if not current_ids.issubset(previous_ids):
                        if not outstanding_flags.filter(reason=reason).exists():
                            create_flag(interaction, reason, user, 'missing_prerequisite')
                    else:
                        resolve_flag(outstanding_flags, reason)

    #Rule 3: Check for a required attribute
    required_attributes = interaction.task.indicator.required_attributes.all() 
    if required_attributes.exists():
        respondent_attrs = set(interaction.respondent.special_attribute.values_list('id', flat=True))
        
        for attribute in required_attributes:
            reason = (
                f'Task "{interaction.task.indicator.name}" requires the respondent to have the special attribute "{attribute.name}". This interaction will be flagged so long as the respondent does not have the selected attribute.'
            )
            
            if attribute.id not in respondent_attrs:
                if not outstanding_flags.filter(reason=reason).exists():
                    create_flag(interaction, reason, user, 'missing_prerequisite')
            else:
                resolve_flag(outstanding_flags, reason)
                


def update_m2m_status(model, through_model, respondent, name_list, related_field='attribute'):
    """
    Handles creating/updating M2M status fields like KP or Disability.

    Parameters:
    - model: The FK-related model (e.g., KeyPopulation or DisabilityType)
    - through_model: The intermediate model (e.g., KeyPopulationStatus or DisabilityStatus)
    - respondent: The Respondent instance
    - name_list: List of names to set
    - related_field: Name of the FK field on the through model pointing to the related model (default 'attribute')
    """
    # Clear existing statuses
    through_model.objects.filter(respondent=respondent).delete()

    # Create or get status items
    related_instances = []
    for name in name_list:
        related_obj, _ = model.objects.get_or_create(name=name)
        # Create the through relationship
        through_model.objects.get_or_create(respondent=respondent, **{related_field: related_obj})
        related_instances.append(related_obj)

    return related_instances

def get_enum_choices(enum_class, exclude: set = None):
    '''
    Helper function to get choices and labels for each field.
    '''
    exclude = exclude or set()
    return [
        {"value": choice.value, "label": choice.label}
        for choice in enum_class
        if choice.value not in exclude
    ]

def check_event_perm(user, event, project_id):
        '''
        Since interactions can be tied to events, this helper determines if a user should have access to this
        event.
        '''

        #admins can access everything
        if user.role == 'admin':
            return True
        # Check if the user’s org is the host or their child org is the host
        valid_host = (
            user.organization == event.host or
            ProjectOrganization.objects.filter(
                parent_organization=user.organization,
                project__id=project_id,
                organization=event.host
            ).exists()
        )

        # Check if the user’s org is explicitly listed as a participant
        is_participant = EventOrganization.objects.filter(
            event=event,
            organization=user.organization
        ).exists()

        if valid_host or is_participant:
            return True
        return False
        

def topological_sort(tasks):
    from collections import defaultdict, deque

    graph = defaultdict(list)
    in_degree = defaultdict(int)

    for task in tasks:
        if task.indicator.prerequisite:
            graph[task.indicator.prerequisite.id].append(task.indicator.id)
            in_degree[task.indicator.id] += 1
        else:
            in_degree[task.indicator.id] += 0

    id_map = {task.indicator.id: task for task in tasks}

    queue = deque([id for id in in_degree if in_degree[id] == 0])
    sorted_ids = []

    while queue:
        current = queue.popleft()
        sorted_ids.append(current)
        for dependent in graph[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(sorted_ids) != len(tasks):
        raise Exception("Cycle detected in prerequisites")
    
    return [id_map[i] for i in sorted_ids]

def dummy_dob_calc(age_range, created_at):
    '''
    Helper function to calcuate a dummy DOB based on the rough midpoint of an age range. 
    '''
    midpoint_ages = {
        'under_1': 1,
        '1_4': 2,
        '5_9': 7,
        '10_14': 12,
        '15_19': 17, 
        '20_24': 22,
        '25_29': 27,
        '30_34': 32, 
        '35_39': 37, 
        '40_44': 42,
        '45_49': 47,
        '50_54': 52,
        '55_59': 57,
        '60_64': 62,
        '65_plus': 67,
    }
    midpoint_age = midpoint_ages.get(age_range.lower())
    if midpoint_age is not None:
        ref_date = created_at.date() if created_at else date.today()
        dummy_dob = ref_date.replace(year=ref_date.year - midpoint_age)

        return dummy_dob
    return None

def calculate_age_range(dob):
        '''
        Helper function to convert sort a given age within our beheamoth age ranges. Seriously, how many do we
        need?
        '''
        if not dob:
            return
        
        if isinstance(dob, str):
            dob = date.fromisoformat(dob)
        # If dob is a tuple, assume (year, month, day)
        elif isinstance(dob, tuple) and len(dob) == 3:
            dob = date(*dob)
        # Optionally, handle datetime objects
        elif isinstance(dob, datetime):
            dob = dob.date()
        today = date.today()

        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        
        if age < 1:
            age_range = Respondent.AgeRanges.U1
        elif age <= 4:
            age_range = Respondent.AgeRanges.O_4
        elif age <= 9:
            age_range = Respondent.AgeRanges.F_9
        elif age <= 14:
            age_range = Respondent.AgeRanges.T_14
        elif age <= 19:
            age_range = Respondent.AgeRanges.FT_19
        elif age <= 24:
            age_range = Respondent.AgeRanges.T_24
        elif age <= 29:
            age_range = Respondent.AgeRanges.T4_29
        elif age <= 34:
            age_range = Respondent.AgeRanges.TH_34
        elif age <= 39:
            age_range = Respondent.AgeRanges.T5_39
        elif age <= 44:
            age_range = Respondent.AgeRanges.F0_44
        elif age <= 49:
            age_range = Respondent.AgeRanges.F5_49
        elif age <= 54:
            age_range = Respondent.AgeRanges.FF_55
        elif age <= 59:
            age_range = Respondent.AgeRanges.F4_59
        elif age <= 64:
            age_range = Respondent.AgeRanges.S0_64
        else:
            age_range = Respondent.AgeRanges.O65
        return age_range