# apps/core/models.py

from django.db import models


class SystemConfig(models.Model):
    """
    Stores global configuration for the application.
    Only ONE row should ever exist (singleton pattern).
    
    Why: The wood quantity formula uses a divisor (e.g. 144 or 1728).
    Instead of hardcoding it, we store it here so any company
    can change it without touching code.
    """

    company_name = models.CharField(
        max_length=255,
        default='My Company',
        help_text="Your company name, shown in reports and headers."
    )

    wood_divisor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=144.00,
        help_text=(
            "Divisor used in wood quantity formula: "
            "(W × B × L × Pieces) ÷ Divisor. "
            "Common values: 144 (inches) or 1728 (cubic inches to CFT)."
        )
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configuration"

    def __str__(self):
        return f"{self.company_name} — Config"

    @classmethod
    def get_config(cls):
        """
        Always returns the single config row.
        Creates it with defaults if it doesn't exist yet.
        
        Usage anywhere in the code:
            config = SystemConfig.get_config()
            divisor = config.wood_divisor
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj