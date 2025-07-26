from projects.models import Project, ProjectOrganization
from django.db.models import Q

def get_valid_orgs(user):
    '''
    Quick helper to pull a general list of child orgs plus the users own org.
    '''
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

def test_child_org(user, organization, project):
    '''
    Helper to determine if the organization is a child org
    '''
    if user.role in ['client', 'admin']:
        return True
    if user.role not in ['meofficer', 'manager']:
        return False
    return ProjectOrganization.objects.filter(organization=organization, parent_organization=user.organization, project=project).exists()





class ProjectPermissionHelper:
    '''
    This permission helper streamlines the process for creating project activites and the like. It automatically
    handles org assignment based on the user's role/their child organizations and the inputted settings.

    It is useful for managing those models like project activities/deadlines that can have many orgs.
    '''
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
        '''
        Helper method to make sure that the organization is actually in the project, if a project is provided.
        '''
        if self.user.role == 'admin':
            return True
        if not self.project:
            return False
        return ProjectOrganization.objects.filter(
            organization=self.user.organization,
            project=self.project
        ).exists()

    def filter_queryset(self, queryset):
        '''
        Filter a given model to only include the correct orgs.
        '''
        if self.user.role not in ['meofficer', 'manager', 'client', 'admin']:
            return queryset.none()
        
        if self.user.role == 'admin':
            return queryset

        if self.user.role == 'client' and self.user.client_organization:
            return queryset.filter(project__client=self.user.client_organization)
        
        if self.project and not self.verify_in_project():
            return queryset.none()
        
        #view visible to all, if their an active participant, or if it's their childs
        filters = Q(**{self.public_flag: True}) | \
                  Q(**{self.org_field: self.org}) | \
                  Q(**{f'{self.org_field}__in': self.child_orgs})
        
        #allow children to see items that their parents have marked as cascaded
        if self.parent_org:
            filters |= Q(**{
                self.org_field: self.parent_org,
                self.cascade_flag: True
            })


        return queryset.filter(filters).filter(project__status=Project.Status.ACTIVE).distinct()

    def alter_switchboard(self, data, instance=None):
        '''
        Help manage the process of creating events, especially assigning orgs so that users don't have to wory
        about this on the front end. 

        Basically if their not an admin, limit it to their org and their child org if cascade flag is true.
        '''
        orgs = data.get(self.org_field) or []
        org_ids = [org.id for org in orgs]

        #other roles have no access
        if self.user.role not in ['admin', 'meofficer', 'manager']:
            return {'success': False, 'data': 'You do not have permission to edit project details.'}
        
        #admins can do whatever
        if self.user.role == 'admin':
            return {'success': True, 'data': data}

        #prevent editing other orgs stuff
        if self.project and not self.verify_in_project():
            return {'success': False, 'data': 'You may not edit details for projects you are not a member of.'}

        #also prevent editing activities that you may be related to but do not own (or children own)
        if instance and hasattr(instance, 'created_by'):
            instance_org = instance.created_by.organization
            if instance_org != self.org and instance_org not in self.child_orgs:
                return {'success': False, 'data': 'You may not edit details related to other organizations.'}

        # Default to user's org if none provided, since for non-admins an org is required
        if not orgs:
            orgs = [self.org]
            org_ids = [self.org.id]

        #prevent non-admins from making public material
        if data.get(self.public_flag):
            return {'success': False, 'data': 'You do not have permission to create project-wide edits.'}

        #also prevent them from adding orgs they are not related to
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
        '''
        Test delete privlleges
        '''
        if self.user.role == 'admin':
            return True
        
        instance_org = instance.created_by.organization
        if self.org == instance_org or instance_org in self.child_orgs:
            return True
        
        return False