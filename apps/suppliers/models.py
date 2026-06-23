# apps/suppliers/models.py

from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal


class Supplier(models.Model):
    """
    A company that supplies one or more resources.

    Future fields: address, email, payment_terms,
                   lead_time_days, performance_score
    """
    supplier_name = models.CharField(
        max_length=255,
        unique=True,
        help_text="Full name of the supplier company."
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Primary contact number."
    )
    gst_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="GST registration number."
    )
    active = models.BooleanField(
        default=True,
        help_text="Inactive suppliers are hidden from resource linking."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['supplier_name']
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"

    def __str__(self):
        return self.supplier_name

    @property
    def resource_count(self):
        return self.resource_links.filter(active=True).count()


class ResourceSupplier(models.Model):
    """
    Explicit Many-to-Many join table between Resource and Supplier.

    Rate lives HERE, not on Resource, because the price of a material
    depends on WHO is selling it, not on the material itself.

    preferred=True means the costing engine uses this supplier's rate
    for all BOM calculations involving this resource.

    If no supplier is marked preferred, the costing engine
    automatically uses the lowest active supplier rate.

    Future fields:
        stock_available (bool)   → is this supplier currently in stock?
        lead_time_days  (int)    → how many days for delivery?
        last_quoted_at  (date)   → when was this rate last confirmed?
    """

    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.CASCADE,
        related_name='supplier_links',
    )
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name='resource_links',
    )

    # The price this supplier charges for this resource
    supplier_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="This supplier's rate per unit for this resource."
    )

    # Mark one supplier as the default for costing
    preferred = models.BooleanField(
        default=False,
        help_text=(
            "If True, the costing engine uses this supplier's rate. "
            "Only one supplier per resource should be preferred."
        )
    )

    # Allows disabling a supplier link without deleting it
    active = models.BooleanField(
        default=True,
        help_text="Inactive links are ignored by the costing engine."
    )

    notes = models.TextField(
        blank=True,
        help_text="Any notes about this supplier-resource relationship."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['resource', 'supplier']]
        ordering = ['-preferred', 'supplier_rate']
        verbose_name = "Resource Supplier"
        verbose_name_plural = "Resource Suppliers"

    def __str__(self):
        preferred_tag = ' ★' if self.preferred else ''
        return (
            f"{self.supplier.supplier_name}"
            f" → {self.resource.resource_name}"
            f" @ ₹{self.supplier_rate}{preferred_tag}"
        )