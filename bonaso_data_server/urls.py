
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/organizations/', include('organizations.urls')),
    path('api/record/', include('respondents.urls')),
    path('api/indicators/', include('indicators.urls')),
    path('api/activities/', include('events.urls')),
    path('api/manage/', include('projects.urls')),
    path('api/profiles/', include('profiles.urls')),
    path('api/analysis/', include('analysis.urls')),
    path('api/messages/', include('messaging.urls')),
    path('api/uploads/', include('uploads.urls')),
    path('api/social/', include('social.urls')),
    path('api/flags/', include('flags.urls')),

    path('api/tests/', include('testing_utils.urls')), #for use with e2e testing only
]
