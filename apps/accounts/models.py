# apps/accounts/models.py

from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    """
    Per-user role and display language. Auto-created for every User by
    apps.accounts.signals — see CLAUDE.md Authentication section.

    Source of truth:
        - is_staff stays authoritative for "admin" (Django admin, MFA
          middleware and @admin_required all read it).
        - role is authoritative for "carpenter".
    The two are kept in sync both ways: saving a profile updates
    user.is_staff, and saving a User with a changed is_staff updates the
    role (see signals.py). A carpenter can therefore never be staff.
    """

    ROLE_ADMIN     = 'admin'
    ROLE_VIEWER    = 'viewer'
    ROLE_CARPENTER = 'carpenter'
    ROLE_CHOICES = [
        (ROLE_ADMIN,     'Admin'),
        (ROLE_VIEWER,    'Viewer'),
        (ROLE_CARPENTER, 'Carpenter'),
    ]

    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('ta', 'தமிழ் (Tamil)'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_VIEWER)
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en')

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'{self.user.username} ({self.get_role_display()})'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Push the role onto is_staff. queryset.update() (not user.save())
        # so the User post_save signal doesn't run again.
        should_be_staff = self.role == self.ROLE_ADMIN
        if self.user.is_staff != should_be_staff:
            type(self.user).objects.filter(pk=self.user_id).update(is_staff=should_be_staff)
            self.user.is_staff = should_be_staff
