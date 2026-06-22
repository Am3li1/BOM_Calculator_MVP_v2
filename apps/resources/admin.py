# apps/resources/admin.py

from django.contrib import admin
from .models import Resource, ResourceCategory


@admin.register(ResourceCategory)
class ResourceCategoryAdmin(admin.ModelAdmin):
    list_display  = ['name', 'sort_order', 'active']
    list_editable = ['sort_order', 'active']
    search_fields = ['name']
    ordering      = ['sort_order', 'name']


@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display   = ['resource_name', 'category', 'unit', 'rate', 'active']
    list_filter    = ['category', 'active']
    search_fields  = ['resource_name', 'category']
    list_editable  = ['rate', 'active']
    ordering       = ['category', 'resource_name']