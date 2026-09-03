# apps/quotations/models.py
from django.db import models
from django.conf import settings

CUSTOMER_TYPE_CHOICES = [
    ('registered', 'Registered Dealer'),
    ('unregistered', 'Small Customer'),
]


class MarkupTier(models.Model):
    """
    Predefined markup percentages staff pick from, instead of typing a
    free-text number per line (which was error-prone — see PROJECT_STATUS.md,
    a stray 1000% typo silently failed validation).
    """
    name = models.CharField(max_length=100)          # e.g. "Standard Retail", "Wholesale", "Dealer"
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['percentage']

    def __str__(self):
        return f"{self.name} ({self.percentage}%)"


class Customer(models.Model):
    name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    state = models.CharField(max_length=50)  # required — drives CGST/SGST vs IGST
    gst_number = models.CharField(max_length=20)  # required
    customer_type = models.CharField(
        max_length=15,
        choices=CUSTOMER_TYPE_CHOICES,
        default='unregistered',
    )
    tally_ledger_name = models.CharField(
        max_length=200, blank=True,
        help_text="Exact ledger name as it exists in Tally. Leave blank to use customer name."
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def resolved_tally_ledger(self):
        return self.tally_ledger_name or self.name

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Quotation(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('sent', 'Sent'),
        ('accepted', 'Accepted'), ('rejected', 'Rejected'),
    ]

    quotation_number = models.CharField(max_length=30, unique=True)  # e.g. QTN-2026-0001
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='quotations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Snapshot totals — rolled up from QuotationItem at save time.
    # GST is per-line (rate depends on each product's HSN), so there is
    # deliberately no single quotation-level gst_percent field.
    total_taxable = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_sgst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_igst = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tally_pushed = models.BooleanField(default=False)
    tally_pushed_at = models.DateTimeField(null=True, blank=True)
    tally_last_response = models.TextField(blank=True)  # raw XML response, for debugging failures

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.quotation_number

    @property
    def tax_summary(self):
        """
        Groups QuotationItem rows by GST rate for the printed tax breakdown
        table (e.g. 'Taxable @18%: ₹X, CGST @9%: ₹Y, SGST @9%: ₹Z').
        Computed on the fly from item snapshots — no separate GST table
        to keep in sync (see PROJECT_STATUS.md decision, Option B).
        """
        from collections import defaultdict
        from decimal import Decimal

        buckets = defaultdict(lambda: {
            'taxable': Decimal('0'), 'cgst': Decimal('0'),
            'sgst': Decimal('0'), 'igst': Decimal('0'),
        })
        for item in self.items.all():
            b = buckets[item.gst_rate]
            b['taxable'] += item.base_cost * item.quantity + (
                item.base_cost * item.markup_percent / 100 * item.quantity
            )
            b['cgst'] += item.cgst_amount
            b['sgst'] += item.sgst_amount
            b['igst'] += item.igst_amount

        return sorted(
            [{'rate': rate, **totals} for rate, totals in buckets.items()],
            key=lambda x: x['rate']
        )


class QuotationItem(models.Model):
    TAX_TYPE_CHOICES = [('CGST_SGST', 'CGST + SGST'), ('IGST', 'IGST')]

    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT)

    # Snapshots — frozen at creation so a later rate/HSN change on the
    # product never silently alters an already-issued quotation.
    base_cost = models.DecimalField(max_digits=12, decimal_places=2)
    markup_tier = models.ForeignKey(MarkupTier, on_delete=models.PROTECT, null=True, blank=True)
    markup_percent = models.DecimalField(max_digits=5, decimal_places=2)  # snapshot of tier.percentage at save time
    quantity = models.PositiveIntegerField(default=1)
    hsn_code = models.CharField(max_length=10, blank=True)
    gst_rate = models.DecimalField(max_digits=4, decimal_places=2)

    tax_type = models.CharField(max_length=10, choices=TAX_TYPE_CHOICES)
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def marked_up_price(self):
        return self.base_cost + (self.base_cost * self.markup_percent / 100)

    @property
    def line_subtotal(self):
        return self.marked_up_price * self.quantity


class TallyLedgerMapping(models.Model):
    """
    Maps a (GST rate, customer type) pair to the EXACT ledger names as they
    exist in Tally. Ledger names in Tally are hand-typed and inconsistent
    (see PROJECT_STATUS.md — real export had "Regisetered" typo'd), so this
    must be admin-editable data, never generated from a format string.
    """
    CUSTOMER_TYPE_CHOICES = CUSTOMER_TYPE_CHOICES  # Alias for backwards compatibility

    gst_rate = models.DecimalField(max_digits=4, decimal_places=2)
    customer_type = models.CharField(max_length=15, choices=CUSTOMER_TYPE_CHOICES)

    sales_ledger_name = models.CharField(max_length=200)   # e.g. "GST Sales@ 5% to Regisetered Dealer"
    cgst_ledger_name = models.CharField(max_length=200)     # e.g. "Output CGST @ 2.5% for Registered Dealer"
    sgst_ledger_name = models.CharField(max_length=200)
    igst_ledger_name = models.CharField(max_length=200, blank=True)  # only needed for inter-state

    class Meta:
        unique_together = ('gst_rate', 'customer_type')

    def __str__(self):
        return f"{self.gst_rate}% — {self.get_customer_type_display()}"