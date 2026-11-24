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

    # AI BOM reviewer (apps/bom/reviewer.py). The public form may call the
    # LLM at most MAX_AI_CHECKS times per link — the link is the only
    # credential, so this caps what one leaked link can spend.
    MAX_AI_CHECKS = 3
    ai_checks_used = models.PositiveSmallIntegerField(default=0)
    ai_reviewed_at = models.DateTimeField(
        null=True, blank=True,
        help_text='When the AI reviewer last checked this list (empty = never checked).',
    )

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


class SubmissionFinding(models.Model):
    """
    One question the AI reviewer raised about a submission ("Did you
    forget Hinge?", "Is 40 the right quantity?"), what the carpenter
    answered, and — once an admin approves — whether the final BOM agreed
    with it. These rows are the reviewer's labelled training data: the
    feedback loop in apps/bom/reviewer.py learns from them. Never costed.
    """

    KIND_MISSING   = 'missing'
    KIND_COMPANION = 'companion'
    KIND_QUANTITY  = 'quantity'
    KIND_DIMENSION = 'dimension'
    KIND_OTHER     = 'other'
    KIND_CHOICES = [
        (KIND_MISSING,   'Possibly missing'),
        (KIND_COMPANION, 'Usually used together'),
        (KIND_QUANTITY,  'Unusual quantity'),
        (KIND_DIMENSION, 'Unusual measurement'),
        (KIND_OTHER,     'Other'),
    ]

    SOURCE_CHOICES = [
        ('stats', 'Learned from BOMs'),
        ('ai',    'AI model'),
    ]

    RESPONSE_ADDED     = 'added'
    RESPONSE_CHANGED   = 'changed'
    RESPONSE_KEPT      = 'kept'
    RESPONSE_DISMISSED = 'dismissed'
    RESPONSE_CHOICES = [
        (RESPONSE_ADDED,     'Added it'),
        (RESPONSE_CHANGED,   'Changed it'),
        (RESPONSE_KEPT,      'Said it is correct'),
        (RESPONSE_DISMISSED, 'Said not needed'),
    ]

    OUTCOME_CONFIRMED = 'confirmed'
    OUTCOME_REJECTED  = 'rejected'
    OUTCOME_CHOICES = [
        (OUTCOME_CONFIRMED, 'Approved BOM agreed with the AI'),
        (OUTCOME_REJECTED,  'Approved BOM did not follow the AI'),
    ]

    submission = models.ForeignKey(BOMSubmission, on_delete=models.CASCADE, related_name='findings')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='stats')
    resource = models.ForeignKey(
        'resources.Resource', on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    part_name = models.CharField(max_length=200, blank=True)
    message = models.TextField(help_text='The question, in English.')
    evidence = models.CharField(max_length=500, blank=True)
    suggested_value = models.CharField(max_length=50, blank=True)
    current_value = models.CharField(max_length=100, blank=True,
                                     help_text='What the carpenter had entered when this was raised.')
    carpenter_response = models.CharField(max_length=20, choices=RESPONSE_CHOICES, blank=True)
    admin_outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.get_kind_display()}: {self.message[:60]}'
