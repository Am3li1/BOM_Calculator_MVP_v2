from django.contrib import admin
from .models import ImportLog


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    has_add_permission    = lambda self, request: False
    has_change_permission = lambda self, request, obj=None: False
    # Columns shown in the list view
    list_display = [
        'created_at', 'import_type', 'status', 'file_name',
        'resources_imported', 'products_imported', 'bom_rows_imported',
        'wood_parts_imported', 'suppliers_imported', 'validation_error_count',
    ]

    # Sidebar filters
    list_filter = ['status', 'import_type']

    # Search box — searches across these fields
    search_fields = ['file_name']

    # Newest first
    ordering = ['-created_at']

    # All fields are read-only — logs are audit records, never edited
    readonly_fields = [
        'created_at', 'uploaded_by', 'file_name', 'file_path',
        'status', 'import_type',
        'products_imported', 'resources_imported', 'bom_rows_imported',
        'wood_parts_imported', 'suppliers_imported',
        'error_log', 'validation_error_count',
    ]