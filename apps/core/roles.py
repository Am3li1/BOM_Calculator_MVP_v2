# apps/core/roles.py
#
# Role lookups for request.user. Reads the UserProfile through the
# reverse OneToOne (user.profile) so apps.core never imports
# apps.accounts models directly.

ROLE_ADMIN     = 'admin'
ROLE_VIEWER    = 'viewer'
ROLE_CARPENTER = 'carpenter'


def get_role(user):
    """'admin' / 'viewer' / 'carpenter', or None for anonymous users."""
    if user is None or not user.is_authenticated:
        return None
    # Carpenter is checked first so the most restricted role wins if
    # is_staff and role ever disagree (they're kept in sync, but fail closed).
    profile = getattr(user, 'profile', None)
    if profile is not None and profile.role == ROLE_CARPENTER:
        return ROLE_CARPENTER
    if user.is_staff:
        return ROLE_ADMIN
    return ROLE_VIEWER


def is_carpenter(user):
    return get_role(user) == ROLE_CARPENTER
