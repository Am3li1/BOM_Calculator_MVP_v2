# apps/core/context_processors.py

from apps.core.roles import get_role, ROLE_CARPENTER


def user_role(request):
    """Exposes user_role / is_carpenter to templates. Display only — the
    view decorators are what actually enforce access."""
    role = get_role(getattr(request, 'user', None))
    return {
        'user_role': role,
        'is_carpenter': role == ROLE_CARPENTER,
    }
