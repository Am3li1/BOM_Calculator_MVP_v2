# apps/core/decorators.py

from functools import wraps
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    """
    Decorator for views that require the user to be a staff member.

    - If not logged in    → redirected to login (via @login_required behaviour)
    - If logged in but not staff → 403 Forbidden
    - If staff            → view runs normally

    Usage:
        @login_required          ← still needed to handle unauthenticated users
        @admin_required
        def my_view(request):
            ...

    Who is "admin" here?
        Any user with is_staff=True in Django admin.
        Set this via: Django admin → Users → edit user → Staff status ✓
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_staff:
            raise PermissionDenied   # Django renders 403.html automatically
        return view_func(request, *args, **kwargs)
    return wrapper