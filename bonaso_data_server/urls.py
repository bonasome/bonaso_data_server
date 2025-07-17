
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
    path('api/uploads/', include('uploads.urls')),
]
