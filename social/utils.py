from projects.models import ProjectOrganization

def user_has_post_access(user, post):
    '''
    Helper function to determine if a user should have access to a post. Assumes that all tasks belong to the 
    same org, which is enforced in the serializer
    '''
    task = post.tasks.first() #just get the first for comparison since key details should be shared
    return (
        task.organization == user.organization or #is users org
        ProjectOrganization.objects.filter( #or is child org
            organization=task.organization,
            project=task.project,
            parent_organization=user.organization
        ).exists()
    )