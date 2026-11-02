# apps/carpenter/context_processors.py

from apps.core.roles import get_role, ROLE_ADMIN


def pending_submissions(request):
    """Count of carpenter submissions waiting for review — sidebar badge,
    admins only (the query is skipped for everyone else)."""
    if get_role(getattr(request, 'user', None)) != ROLE_ADMIN:
        return {}
    from .models import BOMSubmission
    return {
        'pending_submission_count': BOMSubmission.objects.filter(
            status=BOMSubmission.STATUS_PENDING
        ).count(),
    }
