# apps/core/models.py

from django.db import models


class SystemConfig(models.Model):
    """
    Stores global configuration for the application.
    Only ONE row should ever exist (singleton pattern).

    Note: wood_divisor used to live here but was removed — the wood
    quantity divisor is no longer a global setting. The two built-in
    material_type formulas use a fixed constant (see
    apps.bom.models._BUILTIN_DIVISOR), and custom formulas
    (Resource/WoodPart.formula_expression) have the user type the
    divisor literally, e.g. ".../166".
    """

    company_name = models.CharField(
        max_length=255,
        default='My Company',
        help_text="Your company name, shown in reports and headers."
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
            company = config.company_name
        """
        obj, created = cls.objects.get_or_create(pk=1)
        return obj