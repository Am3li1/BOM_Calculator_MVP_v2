# apps/resources/models.py

from django.db import models


class Resource(models.Model):
    """
    Represents a raw material, labour type, or overhead cost item.
    
    Examples:
        - Teak Wood (Wood, SFT, rate=85.00)
        - Labour (Labour, NOS, rate=150.00)
        - Hardware (Hardware, NOS, rate=25.00)
    
    Why 'rate' lives here and NOT in BOMItem:
        Rate must be a single source of truth.
        When a rate changes, ALL product costs update automatically
        because they always read rate from this table.
    """

    # Category choices — add more as needed
    CATEGORY_CHOICES = [
        ('Wood', 'Wood'),
        ('Ply', 'Ply'),
        ('MDF', 'MDF'),
        ('Hardware', 'Hardware'),
        ('Labour', 'Labour'),
        ('Finishing', 'Finishing'),
        ('Packing', 'Packing'),
        ('Other', 'Other'),
    ]

    resource_name = models.CharField(
        max_length=255,
        help_text="Name of the resource e.g. Teak Wood, Labour, Hardware"
    )

    category = models.CharField(
        max_length=100,
        choices=CATEGORY_CHOICES,
        default='Other',
        help_text="Category this resource belongs to."
    )

    unit = models.CharField(
        max_length=50,
        help_text="Unit of measurement e.g. SFT, CFT, NOS, KG, RFT"
    )

    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Current rate per unit. Changing this instantly updates all product costs."
    )

    active = models.BooleanField(
        default=True,
        help_text="Inactive resources are hidden from BOM selection but data is preserved."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'resource_name']
        verbose_name = "Resource"
        verbose_name_plural = "Resources"
        # Prevent two resources with the same name in same category
        unique_together = [['resource_name', 'category']]

    def __str__(self):
        return f"{self.resource_name} ({self.category}) — ₹{self.rate}/{self.unit}"