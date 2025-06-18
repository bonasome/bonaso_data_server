from django.contrib import admin
from projects.models import Project, Target, Client, Task

admin.site.register(Project)
admin.site.register(Client)
admin.site.register(Task)
admin.site.register(Target)