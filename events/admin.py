from django.contrib import admin
from events.models import Event, DemographicCount


'''
Admin doesn't support JWT natively and I don't feel like adding it so we're really only using this for dev.
Plus we ideally want to keep everything in one place.
'''
admin.site.register(Event)
admin.site.register(DemographicCount)

