from django.apps import apps
from django.db.models import Q
from collections import defaultdict

from respondents.models import Respondent, Interaction
from events.models import Event, DemographicCount
from indicators.models import Indicator
from organizations.models import Organization
from projects.models import Project, Task, ProjectActivity, ProjectDeadline, Target, Client
from social.models import SocialMediaPost
from uploads.models import NarrativeReport

def get_user_activity(user):
    '''
    Helper function to collect a list of all user activity. Not an exact science, but gives an idea of a users 
    activity for a profile page.
    '''
    USER_ACTIVITY_MODELS = [
        Project,
        Task,
        Target,
        Client,
        ProjectActivity,
        ProjectDeadline,
        Event,
        DemographicCount,
        SocialMediaPost,
        NarrativeReport,
        Organization,
        Respondent,
        Interaction,
        Indicator,
    ]

    user_id = user.id
    activity = defaultdict(list)

    for model in USER_ACTIVITY_MODELS:
        field_names = [f.name for f in model._meta.get_fields()]
        has_created = 'created_by' in field_names
        has_updated = 'updated_by' in field_names

        if not (has_created or has_updated):
            continue

        q_obj = Q()
        if has_created:
            q_obj |= Q(created_by_id=user_id)
        if has_updated:
            q_obj |= Q(updated_by_id=user_id)

        qs = model.objects.filter(q_obj)

        # Order by updated_at if available, otherwise fallback to created_at
        if 'updated_at' in field_names:
            qs = qs.order_by('-updated_at')[:125]
        elif 'created_at' in field_names:
            qs = qs.order_by('-created_at')[:125]

        if qs.exists():
            activity[model._meta.label].extend(qs)

    return activity

def get_favorited_object(model_str, obj_id):
    '''
    Helper function to take a model string (app.model) and an id and convert it to a favorite
    '''
    ALLOWED_FAV_MODELS = {
            "respondents.respondent",
            "events.event",
            "projects.project"
        }
    if model_str.lower() not in ALLOWED_FAV_MODELS:
        return {'success': False, 'data': {"detail": "Cannot favorite this item."}}
    try:
        app_label, model_name = model_str.lower().split('.')
        model = apps.get_model(app_label, model_name)
        if not model:
            raise LookupError
    except (ValueError, LookupError):
        return {'success': False, 'data': {"detail": f'"{model_str}" is not a valid model.'}}

    try:
        target_obj = model.objects.get(pk=obj_id)
    except model.DoesNotExist:
        return {'success': False, 'data': {"detail": f"No {model.__name__} with id {obj_id}."}}
    return {'success': True, 'data': model}