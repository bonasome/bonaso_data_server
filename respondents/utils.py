from django.utils.timezone import now
from datetime import date, datetime, timedelta
from respondents.models import InteractionFlag

def create_flag(interaction, reason):
    InteractionFlag.objects.create(
        interaction=interaction,
        reason=reason,
        auto_flagged=True
    )

def resolve_flag(flags_qs, reason):
    to_resolve = flags_qs.filter(reason=reason, resolved=False).first()
    if to_resolve:
        to_resolve.resolved = True
        to_resolve.auto_resolved = True
        to_resolve.resolved_at = now()
        to_resolve.save()


def auto_flag_logic(interaction, downstream=False):
    from respondents.models import Interaction, InteractionFlag, InteractionSubcategory
    if not interaction.interaction_date or not interaction.task or not interaction.respondent:
        return
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

    outstanding_flags = InteractionFlag.objects.filter(
        interaction=interaction,
        auto_flagged=True,
    )

    reason = (
        f'Respondent "{interaction.respondent}" has had an interaction associated '
        f'with task "{interaction.task.indicator.name}" within 30 days of this interaction.'
    )
    if not downstream and not interaction.task.indicator.allow_repeat:
        if Interaction.objects.filter(
            interaction_date__lte=next_thirty_days,
            interaction_date__gte=past_thirty_days,
            respondent=interaction.respondent, task=interaction.task
        ).exclude(pk=interaction.pk).exists():
            if not outstanding_flags.filter(reason=reason).exists():
                create_flag(interaction, reason)
        else:
            resolve_flag(outstanding_flags, reason)
                

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
                    f'Indicator requires task "{prerequisite.name}" to have a valid interaction '
                    f'with this respondent within the past year. Make sure the prerequisite interaction is not in the future.'
                )
            if not prereqs.exists():
                if not outstanding_flags.filter(reason=reason).exists():
                    create_flag(interaction, reason)
            else:
                resolve_flag(outstanding_flags, reason)
                if interaction.task.indicator.match_subcategories_to == prerequisite:
                    most_recent = prereqs.order_by('-interaction_date').first()
                    reason = (f'The selected subcategories for task "{interaction.task.indicator.name}" do'
                        f'not match with the parent interaction associated with task "{most_recent.task.indicator.name}".' 
                        'This interaction will be flagged until the subcategories match.')
                    current_ids = set(
                        InteractionSubcategory.objects.filter(interaction=interaction)
                        .values_list("subcategory_id", flat=True)
                    )
                    previous_ids = set(most_recent.subcategories.values_list('id', flat=True))
                    print('c', current_ids, 'p', previous_ids)
                    if not current_ids.issubset(previous_ids):
                        if not outstanding_flags.filter(reason=reason).exists():
                            create_flag(interaction, reason)
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