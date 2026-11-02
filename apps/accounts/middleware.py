# apps/accounts/middleware.py

from django.conf import settings


class SessionAgeByRoleMiddleware:
    """
    Enforces STAFF_SESSION_AGE / NON_STAFF_SESSION_AGE per request rather
    than only at login — allauth's own LoginForm unconditionally calls
    request.session.set_expiry(0) right after login unless a "remember me"
    checkbox was ticked (there isn't one here), which would otherwise wipe
    out any per-role expiry set at login time. Running this on every
    request corrects that on the very next page load.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)

        if user is not None and user.is_authenticated:
            age = settings.STAFF_SESSION_AGE if user.is_staff else settings.NON_STAFF_SESSION_AGE
            if request.session.get_expiry_age() != age:
                request.session.set_expiry(age)

        return self.get_response(request)
