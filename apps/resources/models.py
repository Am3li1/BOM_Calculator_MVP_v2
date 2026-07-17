# apps/resources/models.py

from django.db import models
from decimal import Decimal

class ResourceCategory(models.Model):
    """
    Stores resource categories as database records.
    Administrators can add/rename/remove without code changes.
    """
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    # material_type / default_unit REMOVED — wrong granularity,
    # Carpentry Materials holds both Teak and Plywood.

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Resource Category"
        verbose_name_plural = "Resource Categories"

    def __str__(self):
        return self.name
class Resource(models.Model):
    """
    Represents a raw material, labour type, or overhead cost item.

    Rate priority chain (what costing actually uses):
        1. manual_override_rate  — if user has deliberately set one
        2. preferred supplier rate — if one supplier is marked preferred
        3. lowest active supplier rate — cheapest available supplier
        4. self.rate — original master rate, ultimate fallback

    This means:
        - Resources with no suppliers → use self.rate (unchanged behaviour)
        - Resources with suppliers → auto-use best available rate
        - User can override any time for business reasons
    """

    resource_name = models.CharField(max_length=255)

    category = models.CharField(
        max_length=100,
        help_text="Category this resource belongs to."
    )

    unit = models.CharField(
        max_length=50,
        help_text="Unit of measurement e.g. cft, sqft, kg, day, nos"
    )

    MATERIAL_TYPE_CHOICES = [
        ('solid_wood', 'Solid Wood (CFT formula)'),
        ('sheet',      'Sheet Material (SFT formula)'),
        ('other',      'Other / Not Dimensional'),
    ]
    material_type = models.CharField(
        max_length=20,
        choices=MATERIAL_TYPE_CHOICES,
        default='other',
        help_text=(
            "Drives WoodPart formula selection. Set to 'Solid Wood' for "
            "Teak/Country Wood (CFT: W×B×L÷divisor), 'Sheet Material' for "
            "Plywood/MDF/PLPB (SFT: W×L, no divisor)."
        ),
    )

    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=(
            "Master rate. Used as fallback when no supplier "
            "links exist."
        )
    )

    # ── Supplier override ─────────────────────────────────────────
    manual_override_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "When set, this rate is used for all costing — "
            "overriding supplier rates. "
            "Clear this field to revert to automatic supplier pricing."
        )
    )

    override_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text=(
            "Optional note explaining why the override was set. "
            "e.g. 'Better quality', 'Existing credit terms'"
        )
    )

    active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'resource_name']
        verbose_name = "Resource"
        verbose_name_plural = "Resources"
        unique_together = [['resource_name', 'category']]

    def __str__(self):
        return (
            f"{self.resource_name} ({self.category})"
            f" — ₹{self.effective_rate}/{self.unit}"
        )

    # ── Rate properties ───────────────────────────────────────────

    @property
    def lowest_supplier_rate(self):
        """
        The cheapest rate among all active supplier links.
        Returns None if no active supplier links exist.

        This is purely informational — it does NOT affect costing
        unless no preferred supplier or override is set.
        """
        active_links = self.supplier_links.filter(active=True)
        if not active_links.exists():
            return None
        cheapest = active_links.order_by('supplier_rate').first()
        return cheapest.supplier_rate

    @property
    def preferred_supplier_rate(self):
        """
        The rate from the supplier marked as preferred.
        Returns None if no preferred supplier is set.

        Preferred ≠ cheapest. The company may prefer a supplier
        for quality, reliability, or payment terms.
        """
        preferred = self.supplier_links.filter(
            preferred=True,
            active=True
        ).first()
        if preferred:
            return preferred.supplier_rate
        return None

    @property
    def effective_rate(self):
        """
        THE rate the costing engine uses. Single source of truth.

        Priority:
            1. manual_override_rate (deliberate business decision)
            2. preferred supplier rate (chosen supplier)
            3. lowest active supplier rate (cheapest available)
            4. self.rate (master rate — no suppliers exist)
        """
        if self.manual_override_rate is not None:
            return self.manual_override_rate

        preferred = self.preferred_supplier_rate
        if preferred is not None:
            return preferred

        lowest = self.lowest_supplier_rate
        if lowest is not None:
            return lowest

        return self.rate

    @property
    def effective_rate_source(self):
        """
        Explains WHERE effective_rate comes from.
        Used in UI to show users what the system is doing.

        Returns a dict:
            source:   'override' | 'preferred' | 'lowest' | 'master'
            label:    Human-readable description
            rate:     The actual rate value
            supplier: Supplier name (or None)
        """
        if self.manual_override_rate is not None:
            return {
                'source':   'override',
                'label':    'Manual Override',
                'rate':     self.manual_override_rate,
                'supplier': None,
                'reason':   self.override_reason or '',
            }

        preferred_link = self.supplier_links.filter(
            preferred=True, active=True
        ).first()
        if preferred_link:
            return {
                'source':   'preferred',
                'label':    'Preferred Supplier',
                'rate':     preferred_link.supplier_rate,
                'supplier': preferred_link.supplier.supplier_name,
                'reason':   '',
            }

        cheapest_link = self.supplier_links.filter(
            active=True
        ).order_by('supplier_rate').first()
        if cheapest_link:
            return {
                'source':   'lowest',
                'label':    'Lowest Supplier Rate',
                'rate':     cheapest_link.supplier_rate,
                'supplier': cheapest_link.supplier.supplier_name,
                'reason':   '',
            }

        return {
            'source':   'master',
            'label':    'Master Rate',
            'rate':     self.rate,
            'supplier': None,
            'reason':   '',
        }
    


