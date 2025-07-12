
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