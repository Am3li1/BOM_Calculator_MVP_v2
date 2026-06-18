from django.contrib import admin
from .models import Resource

@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = ['resource_name', 'category', 'unit', 'rate', 'active']
    list_filter = ['category', 'active']
    search_fields = ['resource_name']