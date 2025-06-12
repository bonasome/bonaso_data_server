
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('users/', include('users.urls')),
    path('organizations/', include('organizations.urls')),
    path('respondents/', include('respondents.urls')),
    path('indicators/', include('indicators.urls')),
    path('projects/', include('projects.urls')),
]
