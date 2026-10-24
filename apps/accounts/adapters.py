# apps/accounts/adapters.py

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect
from django.urls import reverse

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """
    Self-registration is disabled everywhere. Accounts (Admin/Viewer, and
    eventually Carpenter) are created by an existing admin via the User
    Management UI (apps.accounts.views.user_create) — see CLAUDE.md
    Authentication section.
    """

    def is_open_for_signup(self, request):
        return False

    def get_login_redirect_url(self, request):
        # Carpenters are 403'd from the dashboard (and every other
        # cost-bearing page), so send them straight to their own area.
        from apps.core.roles import is_carpenter
        if is_carpenter(request.user):
            return reverse('carpenter:home')
        return super().get_login_redirect_url(request)


class AllowlistSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Google sign-in is for admins only, and only for emails on
    GOOGLE_ALLOWED_ADMIN_EMAILS — see CLAUDE.md Security section. It never
    creates a new User; it only links to an existing is_staff account whose
    email matches, so an admin account must already exist (created via the
    normal User Management UI) before its owner can use Google to sign in.
    """

    def is_open_for_signup(self, request, sociallogin):
        return False

    def pre_social_login(self, request, sociallogin):
        if sociallogin.is_existing:
            return

        email = (sociallogin.user.email or '').strip().lower()
        allowed = {e.strip().lower() for e in settings.GOOGLE_ALLOWED_ADMIN_EMAILS if e.strip()}

        if not email or email not in allowed:
            messages.error(request, 'This Google account is not authorized to sign in.')
            raise ImmediateHttpResponse(redirect('account_login'))

        UserModel = get_user_model()
        try:
            existing_user = UserModel.objects.get(email__iexact=email)
        except UserModel.DoesNotExist:
            messages.error(
                request,
                'No matching admin account found for this Google email. '
                'An administrator must create your account first.',
            )
            raise ImmediateHttpResponse(redirect('account_login'))

        if not existing_user.is_staff:
            messages.error(request, 'Google sign-in is restricted to admin accounts.')
            raise ImmediateHttpResponse(redirect('account_login'))

        sociallogin.connect(request, existing_user)
