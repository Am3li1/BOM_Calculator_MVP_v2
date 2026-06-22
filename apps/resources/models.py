# apps/resources/models.py

from django.db import models


class ResourceCategory(models.Model):
    """
    Stores resource categories as database records — not hardcoded choices.

    This allows administrators to add, rename, or remove categories
    without any code changes.

    Examples:
        Carpentry Materials
        Labour Charges
        Polish Material
        Upholstery
        Miscellaneous
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Category name e.g. Carpentry Materials, Labour Charges"
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        help_text="Lower numbers appear first in dropdowns."
    )
    active = models.BooleanField(
        default=True,
        help_text="Inactive categories are hidden from dropdowns."
    )

    class Meta:
        ordering = ['sort_order', 'name']
        verbose_name = "Resource Category"
        verbose_name_plural = "Resource Categories"

    def __str__(self):
        return self.name


class Resource(models.Model):
    """
    Represents a raw material, labour type, or overhead cost item.

    Examples:
        - Teak Wood (Carpentry Materials, cft, rate=2500)
        - Carpenter  (Labour Charges, day, rate=1125)
        - Fevicol    (Carpentry Materials, kg, rate=286)

    Why 'rate' lives here and NOT in BOMItem:
        Rate is a single source of truth.
        When a rate changes, ALL product costs update automatically
        because BOMItem.cost always reads rate from this table.
    """

    resource_name = models.CharField(
        max_length=255,
        help_text="Name of the resource e.g. Teak Wood, Carpenter"
    )

    # Free text — no hardcoded choices.
    # Category values come from the ResourceCategory table,
    # but stored as a string here so imports always work
    # even if a category doesn't exist in ResourceCategory yet.
    category = models.CharField(
        max_length=100,
        help_text="Category this resource belongs to."
    )

    unit = models.CharField(
        max_length=50,
        help_text="Unit of measurement e.g. cft, sqft, kg, day, nos"
    )

    rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=(
            "Current rate per unit. "
            "Changing this instantly updates all product costs."
        )
    )

    active = models.BooleanField(
        default=True,
        help_text=(
            "Inactive resources are hidden from BOM selection "
            "but data is preserved."
        )
    )

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
            f" — ₹{self.rate}/{self.unit}"
        )