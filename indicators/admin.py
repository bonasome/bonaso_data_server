from django.contrib import admin
from indicators.models import Indicator, IndicatorSubcategory


class IndicatorAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'status', 'created_at')
    filter_horizontal = ('subcategories',)

admin.site.register(Indicator, IndicatorAdmin)