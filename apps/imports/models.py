# apps/imports/models.py

from django.db import models
from django.contrib.auth.models import User


class ImportLog(models.Model):
    """
    Tracks every Excel file upload.
    
    Why: So users can see what was imported, when, by whom,
    and whether it succeeded or had errors. Invaluable for debugging.
    """

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('partial', 'Partial Success'),
        ('failed', 'Failed'),
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

    file_path = models.FileField(
        upload_to='imports/',
        help_text="Stored copy of the uploaded file."
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    # Counts of what was imported
    products_imported = models.IntegerField(default=0)
    resources_imported = models.IntegerField(default=0)
    bom_rows_imported = models.IntegerField(default=0)
    wood_parts_imported = models.IntegerField(default=0)

    # Any errors or warnings from the import
    error_log = models.TextField(
        blank=True,
        help_text="Any validation errors or warnings during import."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Import Log"
        verbose_name_plural = "Import Logs"

    def __str__(self):
        return f"{self.file_name} — {self.status} ({self.created_at.strftime('%d %b %Y %H:%M')})"