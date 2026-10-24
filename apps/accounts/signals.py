# apps/accounts/signals.py

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


def role_for_staff_flag(is_staff):
    return UserProfile.ROLE_ADMIN if is_staff else UserProfile.ROLE_VIEWER


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def sync_user_profile(sender, instance, raw=False, **kwargs):
    """
    Every User gets a UserProfile. Keeps role in step with is_staff when
    is_staff is changed directly (Django admin, createsuperuser, shell):
        is_staff=True              -> role admin
        is_staff=False, role admin -> role viewer
        is_staff=False, carpenter  -> unchanged
    """
    if raw:
        return

    profile = UserProfile.objects.filter(user=instance).first()
    if profile is None:
        UserProfile.objects.create(user=instance, role=role_for_staff_flag(instance.is_staff))
        return

    if instance.is_staff and profile.role != UserProfile.ROLE_ADMIN:
        profile.role = UserProfile.ROLE_ADMIN
        profile.save()
    elif not instance.is_staff and profile.role == UserProfile.ROLE_ADMIN:
        profile.role = UserProfile.ROLE_VIEWER
        profile.save()
