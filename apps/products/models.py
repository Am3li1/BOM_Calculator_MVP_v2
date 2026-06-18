# apps/products/models.py

from django.db import models


class Product(models.Model):
    """
    Represents a finished product whose cost we want to calculate.
    
    Examples:
        - 3-Door Wardrobe (WRD-001)
        - Coffee Table (TBL-002)
    
    Soft Delete:
        We never hard-delete products because historical cost data
        linked to them would break. Instead we mark is_deleted=True.
    """

    product_name = models.CharField(
        max_length=255,
        help_text="Full name of the product e.g. 3-Door Wardrobe with Mirror"
    )

    product_code = models.CharField(
        max_length=100,
        help_text="Unique product code e.g. WRD-001. Must be unique across all non-deleted products."
    )

    active = models.BooleanField(
        default=True,
        help_text="Inactive products are hidden from main views but not deleted."
    )

    is_deleted = models.BooleanField(
        default=False,
        help_text="Soft delete flag. Deleted products are hidden everywhere but data is preserved."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product_name']
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return f"{self.product_code} — {self.product_name}"

    # ── Soft Delete Helper ──────────────────────────────────────────
    def delete(self, *args, **kwargs):
        """
        Override default delete to perform soft delete.
        Calling product.delete() will set is_deleted=True
        instead of removing the row from the database.
        """
        self.is_deleted = True
        self.save()

    # ── Manager Shortcut ────────────────────────────────────────────
    @classmethod
    def active_products(cls):
        """Returns only visible, non-deleted products."""
        return cls.objects.filter(is_deleted=False, active=True)