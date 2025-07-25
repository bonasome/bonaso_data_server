def get_user_field(user):
    return {
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "organization": {
            "id": user.organization.id,
            "name": user.organization.name,
        }
    }
    return None