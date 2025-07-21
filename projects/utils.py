from projects.models import Project, ProjectOrganization
#returns a list of valid org ids
#theoretically should not run for admins/clients
def get_valid_orgs(user):
    if user.role not in ['meofficer', 'manager']:
        return [user.organization.id]

    # Get active projects
    valid_projects = Project.objects.filter(status=Project.Status.ACTIVE)

    # Get child orgs across all active projects where this user is the parent org
    child_orgs = ProjectOrganization.objects.filter(
        project__in=valid_projects,
        parent_organization=user.organization
    ).values_list('organization_id', flat=True)

    # Return both the user’s org and all matched child orgs
    return list(child_orgs) + [user.organization.id]

def is_child_of(user, potential_parent):
    return ProjectOrganization.objects.filter(
        project__status=Project.Status.ACTIVE,
        organization=user.organization,
        parent_organization=potential_parent
    ).exists()