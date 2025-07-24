from projects.models import Project, ProjectOrganization
from django.db.models import Q
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

class ProjectPermissionHelper:
    def __init__(self, user, project=None, org_field='organizations', public_flag='visible_to_all', cascade_flag='cascade_to_children'):
        self.user = user
        self.project = project
        self.org = user.organization
        self.org_field = org_field
        self.public_flag = public_flag
        self.cascade_flag = cascade_flag

        self.org_link = ProjectOrganization.objects.filter(organization=self.org).first()
        self.parent_org = self.org_link.parent_organization if self.org_link else None

        child_org_links = ProjectOrganization.objects.filter(parent_organization=self.org)
        if self.project:
            child_org_links = child_org_links.filter(project=self.project)
        self.child_orgs = [co.organization for co in child_org_links]

    def verify_in_project(self):
        if self.user.role == 'admin':
            return True
        if not self.project:
            return False
        return ProjectOrganization.objects.filter(
            organization=self.user.organization,
            project=self.project
        ).exists()


    def filter_queryset(self, queryset):
        if self.user.role not in ['meofficer', 'manager', 'client', 'admin']:
            return queryset.none()
        
        if self.user.role == 'admin':
            return queryset

        if self.user.role == 'client' and self.user.client_organization:
            return queryset.filter(project__client=self.user.client_organization)
        
        if self.project and not self.verify_in_project():
            return queryset.none()
        
        filters = Q(**{self.public_flag: True}) | \
                  Q(**{self.org_field: self.org}) | \
                  Q(**{f'{self.org_field}__in': self.child_orgs})
        
        if self.parent_org:
            filters |= Q(**{
                self.org_field: self.parent_org,
                self.cascade_flag: True
            })


        return queryset.filter(filters).filter(project__status=Project.Status.ACTIVE).distinct()

    def alter_switchboard(self, data, instance=None):
        orgs = data.get(self.org_field) or []
        org_ids = [org.id for org in orgs]

        if self.user.role not in ['admin', 'meofficer', 'manager']:
            return {'success': False, 'data': 'You do not have permission to edit project details.'}
        
        if self.user.role == 'admin':
            return {'success': True, 'data': data}

        if self.project and not self.verify_in_project():
            return {'success': False, 'data': 'You may not edit details for projects you are not a member of.'}

        if instance and hasattr(instance, 'created_by'):
            instance_org = instance.created_by.organization
            if instance_org != self.org and instance_org not in self.child_orgs:
                return {'success': False, 'data': 'You may not edit details related to other organizations.'}

        # Default to user's org if none provided
        if not orgs:
            orgs = [self.org]
            org_ids = [self.org.id]

        if data.get(self.public_flag):
            return {'success': False, 'data': 'You do not have permission to create project-wide edits.'}

        for org in orgs:
            if org != self.org and org not in self.child_orgs:
                return {'success': False, 'data': 'You may not include organizations that are not your organization or one of your child organizations.'}

        # Add child orgs if cascade is set
        if data.get(self.cascade_flag):
            for co in self.child_orgs:
                if co.id not in org_ids:
                    orgs.append(co)

        parsed_data = data.copy()
        parsed_data[self.org_field] = orgs
        return {'success': True, 'data': parsed_data}

    def destroy(self, instance):
        if self.user.role == 'admin':
            return True
        
        instance_org = instance.created_by.organization
        if self.org == instance_org or instance_org in self.child_orgs:
            return True
        
        return False