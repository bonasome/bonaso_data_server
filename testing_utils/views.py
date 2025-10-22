from django.shortcuts import render
from django.core.management import call_command
from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction

User = get_user_model()
from organizations.models import Organization
from projects.models import Project, Task, Client, ProjectOrganization
from indicators.models import Indicator, Assessment, Option, LogicCondition, LogicGroup
from respondents.models import Respondent, Interaction, KeyPopulation, DisabilityType, Response
from events.models import Event

def create_user():
    org = Organization.objects.create(name='BONASO')
    user = User.objects.create_superuser(
        username='admin',
        email='admin@coolguy.com',
        password='testpass123',
        role='admin',
        organization=org,
    )

@transaction.atomic
def seed_db():
    org = Organization.objects.create(name='Parent Org')
    child_org = Organization.objects.create(name='Child Org')
    other_org = Organization.objects.create(name='Other Org')
    assign_org = Organization.objects.create(name='Unassigned Org')
    client_org = Client.objects.create(name='Client Org')

    manager = User.objects.create_user(username='manager', password='testpass123', role='manager', email='test@test.com', organization=org)
    dc = User.objects.create_user(username='dc', password='testpass123', email='test@test.org', role='data_collector', organization=org)

    assessment = Assessment.objects.create(name='Ass')
    indicator = Indicator.objects.create(name='Test 1', type=Indicator.Type.MULTI, assessment=assessment)
    option1 = Option.objects.create(name='Option 1', indicator=indicator)
    option2 = Option.objects.create(name='Option 2', indicator=indicator)
    option3 = Option.objects.create(name='Option 3', indicator=indicator)

    assessment = Assessment.objects.create(name='Ass')
    indicator2 = Indicator.objects.create(name='Test 2', type=Indicator.Type.MULTI, assessment=assessment, match_options=indicator)
    group = LogicGroup.objects.create(indicator=indicator2, group_operator='AND')
    condition = LogicCondition.objects.create(group=group, source_indicator=indicator, condition_type='any', operator='=')

    indicator3=Indicator.objects.create(name='Test 3', type=Indicator.Type.MULTINT, assessment=assessment)
    option4 = Option.objects.create(name='Option 4', indicator=indicator3)
    option5 = Option.objects.create(name='Option 5', indicator=indicator3)

    social_ind = Indicator.objects.create(name='Social', category=Indicator.Category.SOCIAL)

    project = Project.objects.create(name='Test Project', start='2025-01-01', end='2025-12-31', client=client_org, status='Active')
    org_link = ProjectOrganization.objects.create(organization=org, project=project)
    child_link = ProjectOrganization.objects.create(organization=child_org, parent_organization=org, project=project)
    other_link = ProjectOrganization.objects.create(organization=other_org, project=project)

    other_project = Project.objects.create(name='Normies Should Not See This', start='2025-01-01', end='2025-12-31')

    pti = Task.objects.create(project=project, organization=org, assessment=assessment)

    cti = Task.objects.create(project=project, organization=child_org, assessment=assessment)

    oti = Task.objects.create(project=project, organization=other_org, assessment=assessment)

    event = Event.objects.create(name='Test Event', start='2025-05-01', end='2025-05-02', status=Event.EventStatus.COMPLETED, event_type=Event.EventType.ENGAGEMENT, location='Who Cares?', host=org)
    event.save()

    respondent1 = Respondent.objects.create(
        is_anonymous=False,
        id_no='000010001',
        first_name='Goolius', 
        last_name='Boozler', 
        dob='2000-01-01',
        sex=Respondent.Sex.MALE,
        village='Coral Gables',
        district=Respondent.District.CENTRAL,
        citizenship='BW'
    )
    
    respondent2 = Respondent.objects.create(
        is_anonymous=True,
        age_range=Respondent.AgeRanges.T4_29,
        sex=Respondent.Sex.FEMALE,
        village='Coral Gables',
        district=Respondent.District.CENTRAL,
        citizenship='ZM',
    )
    kp1=KeyPopulation.objects.create(name=KeyPopulation.KeyPopulations.FSW)
    kp2=KeyPopulation.objects.create(name=KeyPopulation.KeyPopulations.LBQ)
    d1=DisabilityType.objects.create(name=DisabilityType.DisabilityTypes.HI)
    d2=DisabilityType.objects.create(name=DisabilityType.DisabilityTypes.VI)
    respondent2.kp_status.set([kp1, kp2])
    respondent2.disability_status.set([d1, d2])
    respondent2.save()

    ir1 = Interaction.objects.create(task=pti, respondent=respondent2, interaction_date='2025-03-5', interaction_location='Over there')
    response1 = Response.objects.create(interaction=ir1, response_option=option1, indicator=indicator)
    response11 = Response.objects.create(interaction=ir1, response_option=option2, indicator=indicator)
    response2 = Response.objects.create(interaction=ir1, response_option=option1, indicator=indicator2)
    response3 = Response.objects.create(interaction=ir1, response_option=option4, response_value='10', indicator=indicator3)
    response4 = Response.objects.create(interaction=ir1, response_option=option5, response_value='12', indicator=indicator3)
    

@csrf_exempt
@require_POST
def reset_db(request):
    if not getattr(settings, "TEST_SETUP", False):
        return JsonResponse({"error": "Not allowed. Don't even play me like that bro."}, status=403)

    db_name = settings.DATABASES['default']['NAME']
    if "bonaso_test_db" not in db_name.lower():
        return JsonResponse({"error": f"Refusing to reset non-test database: {db_name}. Like bro, not even my mom tries to wipe by prod DB."}, status=403)

    call_command('flush', interactive=False)

    create_user()
    seed_db()
    print('Test database reset.')
    return JsonResponse({"status": "ok", "message": "DB reset"})
