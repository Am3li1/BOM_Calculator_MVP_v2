# apps/accounts/middleware.py

from django.conf import settings
from django.urls import reverse, resolve, Resolver404
from allauth.mfa.utils import is_mfa_enabled


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

# Paths a staff user without MFA configured yet must still be able to
# reach — the MFA setup flow itself, logout, and the TOTP challenge page
# allauth shows mid-login (reached before this middleware's "logged in but
# unverified" branch, but kept here too for safety).
_EXEMPT_URL_NAMES = {
    'mfa_index',
    'mfa_activate_totp',
    'mfa_deactivate_totp',
    'mfa_authenticate',
    'mfa_reauthenticate',
    'account_logout',
}


class RequireAdminMFAMiddleware:
    """
    CLAUDE.md Security section: "MFA required for Admin accounts." allauth's
    MFA app makes TOTP available but never mandatory on its own, so this
    middleware closes that gap — any is_staff user without a TOTP
    authenticator enrolled is redirected to the MFA setup page on every
    request until they enroll one.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)

        try:
            url_name = resolve(request.path_info).url_name
        except Resolver404:
            url_name = None

        if (
            user is not None
            and user.is_authenticated
            and user.is_staff
            and url_name not in _EXEMPT_URL_NAMES
            and not request.path.startswith('/static/')
            and not request.path.startswith('/media/')
            and not is_mfa_enabled(user)
        ):
            from django.contrib import messages
            from django.shortcuts import redirect

            messages.warning(
                request,
                'Your account requires two-factor authentication. '
                'Set up an authenticator app to continue.',
            )
            return redirect(reverse('mfa_activate_totp'))

        return self.get_response(request)
