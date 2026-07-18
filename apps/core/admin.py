from django.contrib import admin
from .models import SystemConfig

@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ['company_name', 'updated_at']