from django.contrib import admin
from projects.models import Project, Target, Client

admin.site.register(Project)
admin.site.register(Client)
admin.site.register(Target)