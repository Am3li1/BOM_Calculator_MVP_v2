# apps/quotations/admin.py
from django.contrib import admin
from .models import Customer, Quotation, QuotationItem, MarkupTier, TallyLedgerMapping, Invoice, InvoiceItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone_number', 'state', 'gst_number', 'customer_type', 'active']
    list_filter = ['customer_type', 'active', 'state']
    search_fields = ['name', 'gst_number', 'phone_number']


@admin.register(MarkupTier)
class MarkupTierAdmin(admin.ModelAdmin):
    list_display = ['name', 'percentage', 'active']
    list_filter = ['active']


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 0
    readonly_fields = [
        'product', 'base_cost', 'markup_tier', 'markup_percent', 'quantity',
        'hsn_code', 'gst_rate', 'tax_type', 'cgst_amount', 'sgst_amount',
        'igst_amount', 'line_total',
    ]
    # Line items are calculated + snapshotted server-side in the view
    # (see quotation_create/quotation_edit). Editing them directly in
    # admin would desync them from Quotation's rolled-up totals, so
    # this inline is view-only.
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    list_display = ['quotation_number', 'customer', 'status', 'grand_total', 'tally_pushed', 'created_at']
    list_filter = ['status', 'tally_pushed']
    search_fields = ['quotation_number', 'customer__name']
    inlines = [QuotationItemInline]
    readonly_fields = [
        'quotation_number', 'total_taxable', 'total_cgst', 'total_sgst',
        'total_igst', 'grand_total', 'tally_pushed_at', 'tally_last_response',
    ]
    # Same reasoning as the inline above — totals are computed/rolled up
    # in the view layer, not meant to be hand-edited here.


@admin.register(TallyLedgerMapping)
class TallyLedgerMappingAdmin(admin.ModelAdmin):
    list_display = ['gst_rate', 'customer_type', 'sales_ledger_name', 'cgst_ledger_name', 'sgst_ledger_name', 'igst_ledger_name']
    list_filter = ['customer_type']

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = [
        'product', 'base_cost', 'markup_tier', 'markup_percent', 'quantity',
        'hsn_code', 'gst_rate', 'tax_type', 'cgst_amount', 'sgst_amount',
        'igst_amount', 'line_total',
    ]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'quotation', 'status', 'grand_total', 'invoice_date']
    list_filter = ['status']
    search_fields = ['invoice_number', 'quotation__customer__name']
    inlines = [InvoiceItemInline]
    readonly_fields = [
        'invoice_number', 'quotation', 'status', 'invoice_date', 'created_by',
        'created_at', 'total_taxable', 'total_cgst', 'total_sgst',
        'total_igst', 'grand_total', 'finalized_at',
    ]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != 'draft':
            return [field.name for field in obj._meta.fields]
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return obj is None or obj.status == 'draft'