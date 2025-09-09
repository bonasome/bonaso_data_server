from django.shortcuts import render

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt

User = get_user_model()
from organizations.models import Organization

def create_user():
    org = Organization.objects.create(name='BONASO')
    user = User.objects.create_superuser(
        username='admin',
        email='admin@coolguy.com',
        password='testpass123',
        role='admin',
        organization=org,
    )

@csrf_exempt
@require_POST
def reset_db(request):
    if not getattr(settings, "TEST_SETUP", False):
        return JsonResponse({"error": "Not allowed. Don't even play me like that bro."}, status=403)

    db_name = settings.DATABASES['default']['NAME']
    if "bonaso_test_db" not in db_name.lower():
        return JsonResponse({"error": f"Refusing to reset non-test database: {db_name}. Like bro, not even my mom tries to wipe by prod DB."}, status=403)

    with connection.cursor() as cursor:
        # Disable triggers temporarily to allow truncating all tables with FKs
        cursor.execute("SET session_replication_role = 'replica';")

        # Get all tables in the public schema
        cursor.execute("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public';
        """)
        tables = [row[0] for row in cursor.fetchall()]

        if tables:
            table_list = ", ".join(f'"{t}"' for t in tables)
            cursor.execute(f"TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE;")

        # Re-enable triggers
        cursor.execute("SET session_replication_role = 'origin';")

    create_user()


    return JsonResponse({"status": "ok", "truncated_tables": tables})
