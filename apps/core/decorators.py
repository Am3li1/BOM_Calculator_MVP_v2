# apps/core/decorators.py

from functools import wraps
from django.core.exceptions import PermissionDenied

from apps.core.roles import get_role, is_carpenter, ROLE_ADMIN, ROLE_CARPENTER


def admin_required(view_func):
    """
    Decorator for views that require the user to be a staff member.

    - If not logged in    → redirected to login (via @login_required behaviour)
    - If logged in but not staff → 403 Forbidden
    - If carpenter        → 403 Forbidden (backstop; carpenters are never staff)
    - If staff            → view runs normally

    Usage:
        @login_required          ← still needed to handle unauthenticated users
        @not_carpenter
        @admin_required
        def my_view(request):
            ...

    Who is "admin" here?
        Any user with is_staff=True in Django admin.
        Set this via: Django admin → Users → edit user → Staff status ✓
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff or is_carpenter(request.user):
            raise PermissionDenied   # Django renders 403.html automatically
        return view_func(request, *args, **kwargs)
    return wrapper


def not_carpenter(view_func):
    """
    Blocks the Carpenter role. Goes on EVERY view outside the carpenter
    area — carpenters must never see rates, costs, suppliers or cost
    sheets (CLAUDE.md Security rule 3). Place directly below
    @login_required:

        @login_required
        @not_carpenter
        def product_list(request): ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if is_carpenter(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


def carpenter_required(view_func):
    """
    For the carpenter area only. Allows carpenters and admins (so admins
    can see what carpenters see); viewers get 403.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if get_role(request.user) not in (ROLE_CARPENTER, ROLE_ADMIN):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper
