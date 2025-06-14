from django.contrib import admin

from indicators.models import Indicator, IndicatorSubcategory


class IndicatorAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'status', 'created_at')  # customize as needed
    search_fields = ('code', 'name')
    list_filter = ('status',)

admin.site.register(Indicator, IndicatorAdmin)
