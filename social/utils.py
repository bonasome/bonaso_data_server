def user_has_post_access(user, post):
    return (
        post.task.organization == user.organization or 
        ProjectOrganization.objects.filter(
            organization=post.task.organization,
            project=post.task.project,
            parent_organization=user.organization
        ).exists()
    )