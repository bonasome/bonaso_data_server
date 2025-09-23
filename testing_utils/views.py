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
from indicators.models import Indicator, IndicatorSubcategory
from respondents.models import Respondent, Interaction, InteractionSubcategory, KeyPopulation, DisabilityType
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

    indicator = Indicator.objects.create(code='T101', name='Test 1', indicator_type='respondent')
    cat1 = IndicatorSubcategory.objects.create(name='Cat 1')
    cat2 = IndicatorSubcategory.objects.create(name='Cat 2')
    cat3 = IndicatorSubcategory.objects.create(name='Cat 3')
    indicator.subcategories.set([cat1, cat2, cat3])
    indicator.save()

    dep_indicator = Indicator.objects.create(code='T102', name='Test Dep', indicator_type='respondent')
    dep_indicator.prerequisites.set([indicator])
    dep_indicator.subcategories.set([cat1, cat2, cat3])
    dep_indicator.match_subcategories_to = indicator
    dep_indicator.save()
    
    num_sc_indicator = Indicator.objects.create(code='T103', name='Test Numeric Subcats', indicator_type='respondent', require_numeric=True, allow_repeat=True)
    num_sc_indicator.subcategories.set([cat1, cat2, cat3])
    num_sc_indicator.save()

    num_indicator = Indicator.objects.create(code='T104', name='Test Numeric Only', indicator_type='respondent', require_numeric=True)

    social_ind = Indicator.objects.create(code='S101', name='Social', indicator_type='social')

    project = Project.objects.create(name='Test Project', start='2025-01-01', end='2025-12-31', client=client_org, status='Active')
    org_link = ProjectOrganization.objects.create(organization=org, project=project)
    child_link = ProjectOrganization.objects.create(organization=child_org, parent_organization=org, project=project)
    other_link = ProjectOrganization.objects.create(organization=other_org, project=project)

    other_project = Project.objects.create(name='Normies Should Not See This', start='2025-01-01', end='2025-12-31')

    pti = Task.objects.create(project=project, organization=org, indicator=indicator)
    ptd = Task.objects.create(project=project, organization=org, indicator=dep_indicator)
    ptscn = Task.objects.create(project=project, organization=org, indicator=num_sc_indicator)
    pts = Task.objects.create(project=project, organization=org, indicator=social_ind)

    cti = Task.objects.create(project=project, organization=child_org, indicator=indicator)

    oti = Task.objects.create(project=project, organization=other_org, indicator=indicator)

    event = Event.objects.create(name='Test Event', start='2025-05-01', end='2025-05-02', status=Event.EventStatus.COMPLETED, event_type=Event.EventType.ENGAGEMENT, location='Who Cares?', host=org)
    event.tasks.set([pti, ptd])
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
    ir1 = Interaction.objects.create(task=pti, respondent=respondent2, interaction_date='2025-03-5', interaction_location='Over there')
    ir1sc = InteractionSubcategory.objects.create(interaction=ir1, subcategory=cat1)
    ir2 = Interaction.objects.create(task=ptd, respondent=respondent2, interaction_date='2025-03-5', interaction_location='Over there')
    ir2sc = InteractionSubcategory.objects.create(interaction=ir2, subcategory=cat1)
    ir3 = Interaction.objects.create(task=ptscn, respondent=respondent2, interaction_date='2025-03-5', interaction_location='Over there')
    ir3sc = InteractionSubcategory.objects.create(interaction=ir3, subcategory=cat1, numeric_component=10)
    respondent2.save()

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
