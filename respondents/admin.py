from django.contrib import admin
from respondents.models import Respondent, Interaction, RespondentAttribute, KeyPopulationStatus, DisabilityStatus

@admin.register(RespondentAttribute)
class RespondentAttributeAdmin(admin.ModelAdmin):
    list_display = ['respondent', 'attribute', 'auto_assigned']
    list_filter = ['attribute', 'auto_assigned']
    search_fields = ['respondent__first_name', 'respondent__last_name']

@admin.register(DisabilityStatus)
class DisabilityStatus(admin.ModelAdmin):
    list_display = ['respondent', 'disability']
    list_filter = []
    search_fields = ['respondent__first_name', 'respondent__last_name']

@admin.register(KeyPopulationStatus)
class KeyPopulationStatusAdmin(admin.ModelAdmin):
    list_display = ['respondent', 'key_population']
    list_filter = []
    search_fields = ['respondent__first_name', 'respondent__last_name']

admin.site.register(Respondent)
admin.site.register(Interaction)
