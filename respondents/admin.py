from django.contrib import admin
from respondents.models import Respondent, Interaction, RespondentAttribute, KeyPopulationStatus, DisabilityStatus, HIVStatus, Pregnancy, InteractionSubcategory

'''
Admin doesn't support JWT natively and I don't feel like adding it so we're really only using this for dev.
Plus we ideally want to keep everything in one place.
'''

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

@admin.register(Pregnancy)
class Pregnancy(admin.ModelAdmin):
    list_display = ['respondent', 'term_began', 'term_ended']
    list_filter = []
    search_fields = ['respondent__first_name', 'respondent__last_name']

@admin.register(HIVStatus)
class HIVStatus(admin.ModelAdmin):
    list_display = ['respondent', 'hiv_positive', 'date_positive']
    list_filter = []
    search_fields = ['respondent__first_name', 'respondent__last_name']

@admin.register(InteractionSubcategory)
class InteractionSubcategory(admin.ModelAdmin):
    list_display = ['interaction', 'subcategory', 'numeric_component']

admin.site.register(Respondent)
admin.site.register(Interaction)
