# apps/bom/models.py

from django.db import models
from apps.products.models import Product
from apps.resources.models import Resource


class BOMItem(models.Model):
    """
    Standard Bill of Materials line item.
    
    Represents: "Product X needs Y units of Resource Z"
    
    Example:
        3-Door Wardrobe needs 12.5 SFT of Teak Wood
    
    Key design decision:
        'rate' and 'cost' are NOT stored here.
        Cost = quantity × resource.rate  (always calculated live)
        This ensures rate changes reflect immediately everywhere.
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,       # if product deleted, its BOM items go too
        related_name='bom_items',       # lets us do: product.bom_items.all()
        help_text="The product this BOM line belongs to."
    )

    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT,       # PROTECT: don't allow deleting a resource
        related_name='bom_items',       # that's still in use in a BOM
        help_text="The resource/material being consumed."
    )

    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        help_text="How many units of this resource does this product need?"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['resource__category', 'resource__resource_name']
        verbose_name = "BOM Item"
        verbose_name_plural = "BOM Items"
        # A resource should appear only once per product in standard BOM
        unique_together = [['product', 'resource']]

    def __str__(self):
        return f"{self.product.product_code} | {self.resource.resource_name} × {self.quantity}"

    # ── Calculated Properties ───────────────────────────────────────
    @property
    def rate(self):
        """
        Live rate from the resource's effective rate.
        Uses preferred supplier rate, lowest supplier rate,
        or resource master rate — in that priority order.
        """
        return self.resource.effective_rate

    @property
    def cost(self):
        """
        Calculated automatically. Never stored. Never editable.
        Cost = Quantity × Rate
        """
        return self.quantity * self.rate


class WoodPart(models.Model):
    """
    A dimensional entry for a product.
    Captures physical measurements and calculates material quantity.

    Units are stored per-dimension so that mixed-unit products
    (e.g. width in inches, length in feet) are supported.
    """

    UNIT_CHOICES = [
        ('in',   'Inches'),
        ('ft',   'Feet'),
        ('sqft', 'Square Feet'),
        ('cft',  'Cubic Feet'),
        ('mm',   'Millimeters'),
        ('cm',   'Centimeters'),
        ('m',    'Meters'),
        ('nos',  'Numbers'),
    ]

    FORMULA_CHOICES = [
        ('standard', 'Standard (W × B × L × Pcs ÷ Divisor)'),
        ('area',     'Area (W × L × Pcs ÷ Divisor)'),
        ('custom',   'Custom'),
    ]

    product  = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        related_name='wood_parts',
    )
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.PROTECT,
        related_name='wood_parts',
    )

    part_name = models.CharField(max_length=200)

    # Dimensions
    width   = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    breadth = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    height  = models.DecimalField(
        max_digits=10, decimal_places=4,
        default=0, blank=True,
        help_text="Optional. Use for 3D parts."
    )
    length  = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    pieces  = models.PositiveIntegerField(default=1)

    # Units per dimension
    width_unit   = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )
    breadth_unit = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )
    height_unit  = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )
    length_unit  = models.CharField(
        max_length=10, choices=UNIT_CHOICES, default='in'
    )

    formula_type = models.CharField(
        max_length=20,
        choices=FORMULA_CHOICES,
        default='standard',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['part_name']

    def __str__(self):
        return f'{self.product.product_code} — {self.part_name}'

    @property
    def calculated_quantity(self):
        from apps.core.models import SystemConfig
        from decimal import Decimal
    
        config = SystemConfig.get_config()
        divisor = Decimal(str(config.wood_divisor)) if config.wood_divisor else Decimal('1')
    
        w = Decimal(str(self.width))
        b = Decimal(str(self.breadth))
        h = Decimal(str(self.height)) if self.height else Decimal('1')
        l = Decimal(str(self.length))
        p = Decimal(str(self.pieces))
    
        if self.formula_type == 'area':
            return (w * l * p) / divisor
        else:
            effective_h = h if h > 0 else Decimal('1')
            return (w * b * effective_h * l * p) / divisor


    @property
    def rate(self):
        """
        Live rate from the resource's effective rate.
        """
        return self.resource.effective_rate
    
    @property
    def cost(self):
        """Calculated cost — never stored."""
        return self.calculated_quantity * self.rate
