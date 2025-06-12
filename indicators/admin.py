from django.contrib import admin

from indicators.models import Indicator, IndicatorSubcategory

class IndicatorSubcategoryInline(admin.TabularInline):
    model = IndicatorSubcategory
    extra = 1  # number of empty subcategory forms to show

class IndicatorAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'status', 'created_at')  # customize as needed
    search_fields = ('code', 'name')
    list_filter = ('status',)
    inlines = [IndicatorSubcategoryInline]

admin.site.register(Indicator, IndicatorAdmin)
