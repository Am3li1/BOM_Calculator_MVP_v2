# apps/carpenter/models.py
#
# Staging area for carpenter-submitted BOM data. Nothing here is ever
# costed or read by the cost sheet — an admin approving a submission is
# the only path that copies SubmissionLines into real BOMItem / WoodPart
# records (see apps/bom/views_submissions.py).

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def _new_token():
    # 32 bytes → 43 url-safe chars, ~256 bits of entropy. The link is the
    # only credential on the public form, so it must be unguessable.
    return secrets.token_urlsafe(32)


class BOMSubmission(models.Model):
    """
    One magic link sent to a carpenter, and whatever they submit through
    it. A link is either for one existing product (sent from its BOM
    page) or open (product is None): the carpenter then names a new
    product, optionally starting from a copy of an existing one
    (based_on). Approving an open submission creates the product.

    Status flow:
        open     → link sent, waiting for the carpenter
        pending  → carpenter submitted, waiting for admin review
        approved → admin copied the lines into the BOM
        rejected → admin declined; kept for history
        revoked  → admin killed the link before it was used
    """

    STATUS_OPEN     = 'open'
    STATUS_PENDING  = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_REVOKED  = 'revoked'
    STATUS_CHOICES = [
        (STATUS_OPEN,     'Link sent'),
        (STATUS_PENDING,  'Pending review'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_REVOKED,  'Revoked'),
    ]

    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('ta', 'தமிழ் (Tamil)'),
    ]

    DEFAULT_EXPIRY_DAYS = 7

    product = models.ForeignKey(
        'products.Product',
        on_delete=models.CASCADE,
        null=True, blank=True,
        related_name='submissions',
        help_text='Empty for a new-product link until the submission is approved.',
    )
    new_product_name = models.CharField(
        max_length=255, blank=True,
        help_text='Name the carpenter gave the new product (open links only).',
    )
    based_on = models.ForeignKey(
        'products.Product',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
        help_text='Existing product the carpenter copied the list from, if any.',
    )
    token = models.CharField(max_length=64, unique=True, default=_new_token, editable=False)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='+',
    )
    carpenter_name  = models.CharField(max_length=100, blank=True)
    carpenter_phone = models.CharField(max_length=20, blank=True)
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en')
    note = models.TextField(blank=True, help_text="Carpenter's own note, sent with the submission.")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    expires_at   = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='+',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'BOM Submission'
        verbose_name_plural = 'BOM Submissions'

    def __str__(self):
        who = self.carpenter_name or 'carpenter'
        return f'{self.product_label} — {who} ({self.get_status_display()})'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=self.DEFAULT_EXPIRY_DAYS)
        super().save(*args, **kwargs)

    @property
    def is_new_product(self):
        return self.product_id is None

    @property
    def product_label(self):
        if self.product_id:
            return self.product.product_code
        return f'New: {self.new_product_name}' if self.new_product_name else 'New product'

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def accepts_entries(self):
        """True only while the public link may still be filled in."""
        return self.status == self.STATUS_OPEN and not self.is_expired


class SubmissionLine(models.Model):
    """
    One line of a carpenter submission. Mirrors BOMItem (line_type='bom')
    or WoodPart (line_type='dimension'), but is never costed.
    """

    TYPE_BOM       = 'bom'
    TYPE_DIMENSION = 'dimension'
    TYPE_CHOICES = [
        (TYPE_BOM,       'Material'),
        (TYPE_DIMENSION, 'Dimension'),
    ]

    submission = models.ForeignKey(
        BOMSubmission,
        on_delete=models.CASCADE,
        related_name='lines',
    )
    line_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    resource = models.ForeignKey(
        'resources.Resource',
        on_delete=models.PROTECT,
        related_name='+',
    )

    # Material lines
    quantity = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    # Dimension lines — same shape as WoodPart
    part_name = models.CharField(max_length=200, blank=True)
    width   = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    breadth = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    height  = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    length  = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    width_unit   = models.CharField(max_length=10, blank=True, default='in')
    breadth_unit = models.CharField(max_length=10, blank=True, default='in')
    height_unit  = models.CharField(max_length=10, blank=True, default='in')
    length_unit  = models.CharField(max_length=10, blank=True, default='in')
    pieces = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['line_type', 'id']

    def __str__(self):
        if self.line_type == self.TYPE_BOM:
            return f'{self.resource.resource_name} × {self.quantity}'
        return f'{self.part_name} — {self.resource.resource_name}'
