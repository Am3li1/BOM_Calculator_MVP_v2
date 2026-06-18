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
        Always fetched live from Resource master.
        Never stored. Never editable by users.
        """
        return self.resource.rate

    @property
    def cost(self):
        """
        Calculated automatically. Never stored. Never editable.
        Cost = Quantity × Rate
        """
        return self.quantity * self.resource.rate


class WoodPart(models.Model):
    """
    Represents a single wood/ply/MDF cut piece for a product.
    
    Example:
        3-Door Wardrobe — Top Panel
        Width=24, Breadth=18, Length=72, Pieces=1
        Formula: (24 × 18 × 72 × 1) ÷ 144 = 216 SFT
    
    Why separate from BOMItem?
        Wood parts have dimensional data (W × B × L) that standard
        BOM items don't have. The quantity is derived from dimensions,
        not entered directly.
    """

    FORMULA_CHOICES = [
        ('standard', 'Standard: (W × B × L × Pieces) ÷ Divisor'),
        # Add future formula types here without changing existing data
    ]

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name='wood_parts',
        help_text="The product this wood part belongs to."
    )

    resource = models.ForeignKey(
        Resource,
        on_delete=models.PROTECT,
        related_name='wood_parts',
        help_text="The wood/ply/MDF resource being used."
    )

    part_name = models.CharField(
        max_length=255,
        help_text="Descriptive name for this part e.g. Top Panel, Side Panel, Back Panel"
    )

    width = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Width of the piece (in inches or as per your unit system)."
    )

    breadth = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Breadth/depth of the piece."
    )

    length = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        help_text="Length/height of the piece."
    )

    pieces = models.PositiveIntegerField(
        default=1,
        help_text="How many identical pieces of this part are needed?"
    )

    formula_type = models.CharField(
        max_length=50,
        choices=FORMULA_CHOICES,
        default='standard',
        help_text="Which formula to use for quantity calculation."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['resource__category', 'part_name']
        verbose_name = "Wood Part"
        verbose_name_plural = "Wood Parts"

    def __str__(self):
        return f"{self.product.product_code} | {self.part_name} ({self.resource.resource_name})"

    # ── Calculated Properties ───────────────────────────────────────
    @property
    def calculated_quantity(self):
        """
        System calculates this. Users cannot edit it.
        Formula: (Width × Breadth × Length × Pieces) ÷ Divisor
        Divisor comes from SystemConfig — never hardcoded.
        """
        from apps.core.models import SystemConfig
        divisor = SystemConfig.get_config().wood_divisor
        if divisor == 0:
            return 0
        return (self.width * self.breadth * self.length * self.pieces) / divisor

    @property
    def rate(self):
        """Always fetched live from Resource master."""
        return self.resource.rate

    @property
    def cost(self):
        """
        Wood Cost = Calculated Quantity × Resource Rate
        Never stored. Always calculated.
        """
        return self.calculated_quantity * self.resource.rate