# apps/imports/models.py

from django.db import models
from django.contrib.auth.models import User


class ImportLog(models.Model):
    """
    Tracks every upload attempt — including validation failures.

    Status flow:
        pending          → upload received, processing started
        validation_failed → file was rejected before any DB writes
        success          → all records imported cleanly
        partial          → imported with some warnings
        failed           → critical error during import
    """

    STATUS_CHOICES = [
        ('pending',            'Pending'),
        ('validation_failed',  'Validation Failed'),
        ('success',            'Success'),
        ('partial',            'Partial Success'),
        ('failed',             'Failed'),
    ]

    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        help_text="Which user uploaded this file."
    )

    file_name = models.CharField(
        max_length=255,
        help_text="Original name of the uploaded Excel file."
    )

    # file_path is optional — we don't store the file permanently
    file_path = models.FileField(
        upload_to='imports/',
        blank=True,
        help_text="Stored copy of the uploaded file (optional)."
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Import type — 'full' or the sheet_key for individual imports
    import_type = models.CharField(
        max_length=50,
        default='full',
        help_text="'full' for full workbook, or sheet key for individual."
    )

    # Counts — all default to 0, only set on success
    products_imported   = models.IntegerField(default=0)
    parts_imported = models.IntegerField(default=0)
    resources_imported  = models.IntegerField(default=0)
    bom_rows_imported   = models.IntegerField(default=0)
    wood_parts_imported = models.IntegerField(default=0)
    suppliers_imported  = models.IntegerField(default=0)

    # Validation and import errors
    error_log = models.TextField(
        blank=True,
        help_text="Validation errors or import warnings."
    )

    # How many validation errors were found (0 means clean)
    validation_error_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Import Log"
        verbose_name_plural = "Import Logs"

    def __str__(self):
        return (
            f"{self.file_name} — {self.get_status_display()} "
            f"({self.created_at.strftime('%d %b %Y %H:%M')})"
        )

    @property
    def status_colour(self):
        """Bootstrap colour class for this status."""
        return {
            'pending':           'secondary',
            'validation_failed': 'danger',
            'success':           'success',
            'partial':           'warning',
            'failed':            'danger',
        }.get(self.status, 'secondary')

    @property
    def had_validation_errors(self):
        return self.status == 'validation_failed'