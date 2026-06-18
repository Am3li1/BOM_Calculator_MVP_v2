from django.contrib import admin
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'product_name', 'active', 'is_deleted']
    list_filter = ['active', 'is_deleted']
    search_fields = ['product_name', 'product_code']