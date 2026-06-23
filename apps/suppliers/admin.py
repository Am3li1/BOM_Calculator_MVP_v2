# apps/suppliers/admin.py

from django.contrib import admin
from .models import Supplier, ResourceSupplier


class ResourceSupplierInline(admin.TabularInline):
    model = ResourceSupplier
    extra = 0
    readonly_fields = ['created_at']
    fields = [
        'resource', 'supplier_rate',
        'preferred', 'active', 'notes', 'created_at'
    ]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display  = [
        'supplier_name', 'phone_number',
        'gst_number', 'resource_count', 'active'
    ]
    list_filter   = ['active']
    search_fields = ['supplier_name', 'phone_number', 'gst_number']
    list_editable = ['active']
    inlines       = [ResourceSupplierInline]

    def resource_count(self, obj):
        return obj.resource_count
    resource_count.short_description = 'Resources'


@admin.register(ResourceSupplier)
class ResourceSupplierAdmin(admin.ModelAdmin):
    list_display  = [
        'supplier', 'resource',
        'supplier_rate', 'preferred', 'active'
    ]
    list_filter   = ['preferred', 'active']
    list_editable = ['supplier_rate', 'preferred', 'active']
    search_fields = [
        'supplier__supplier_name',
        'resource__resource_name'
    ]