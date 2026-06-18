from django.contrib import admin
from .models import BOMItem, WoodPart

@admin.register(BOMItem)
class BOMItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'resource', 'quantity']
    search_fields = ['product__product_name', 'resource__resource_name']

@admin.register(WoodPart)
class WoodPartAdmin(admin.ModelAdmin):
    list_display = ['product', 'part_name', 'resource', 'width', 'breadth', 'length', 'pieces']
    search_fields = ['product__product_name', 'part_name']