from django.utils.timezone import now
from datetime import date, datetime, timedelta
from django.db.models import Q
from respondents.models import Interaction, Respondent
from indicators.models import Option
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

def check_logic(c, response_info, assessment, respondent):
    if not c or not response_info or not assessment or not respondent:
        return False

    if c.source_type == 'assessment':
        # Find the prerequisite indicator
        prereq = c.source_indicator
        if not prereq:
            return False
        req_val=None
        # Determine required value based on type
        if prereq.type in ['single', 'multi']:
            req_val = c.condition_type if c.condition_type in ['any', 'none', 'all'] else c.value_option.id
        elif prereq.type in ['boolean']:
            req_val = c.value_boolean
        else:
            req_val = c.value_text
        if not req_val:
            return False
        # Get the actual stored value
        prereq_val = response_info.get(str(c.source_indicator.id), {}).get('value')
        print(prereq_val)
        # Special logic for multi with any/none/all
        if prereq.type == 'multi' and c.condition_type in ['any', 'none', 'all']:
            prereq_val = prereq_val or []
            if req_val == 'any':
                return len(prereq_val) > 0
            elif req_val == 'none':
                return prereq_val in [[], None, ['none']]
            elif req_val == 'all':
                return len(prereq_val) == Option.objects.filter(indicator=prereq).count()

        # Special logic for single with any/none/all
        if prereq.type == 'single' and c.condition_type in ['any', 'none', 'all']:
            # single is a single string or None
            prereq_val = prereq_val or None
            if req_val == 'any':
                return bool(prereq_val)
            elif req_val == 'none':
                return prereq_val in [None, 'none']
            elif req_val == 'all':
                return False  # impossible

        # Multi-select value check
        if prereq.type == 'multi':
            if c.operator == '=':
                return prereq_val and req_val in prereq_val
            if c.operator == '!=':
                return not prereq_val or req_val not in prereq_val
        else:
            # Direct comparison for single/text/boolean
            if c.operator == '=':
                return prereq_val == req_val
            if c.operator == '!=':
                return prereq_val != req_val

        # Greater / Less than comparisons
        if c.operator in ['>', '<'] and prereq.type == 'integer':
            try:
                if c.operator == '>':
                    return float(req_val) < float(prereq_val)
                else:
                    return float(req_val) > float(prereq_val)
            except (TypeError, ValueError):
                return False

        # Contains and not contains (text match)
        if c.operator == 'contains':
            return str(req_val).lower() in str(prereq_val).lower()
        if c.operator == '!contains':
            return str(req_val).lower() not in str(prereq_val).lower()

        return False

    elif c.source_type == 'respondent':
        req_val = c.value_text
        prereq_val = getattr(respondent, c.respondent_field)

        if c.operator == '=':
            return prereq_val == req_val
        if c.operator == '!=':
            return prereq_val != req_val
        return False

    return False

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