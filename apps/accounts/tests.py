from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from allauth.mfa.models import Authenticator


class LoginFlowTests(TestCase):
    """Login now goes through django-allauth (account_login), not the old
    apps.accounts.login_view — see CLAUDE.md Authentication section."""

    def setUp(self):
        self.viewer = User.objects.create_user(username='viewer1', password='correct-pw-123')
        self.admin = User.objects.create_user(
            username='admin1', password='correct-pw-123', is_staff=True
        )

    def test_login_url_resolves_to_allauth(self):
        response = self.client.get(reverse('account_login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'account/login.html')

    def test_self_signup_is_closed(self):
        # No account_signup URL is wired in config/urls.py at all.
        response = self.client.get('/accounts/signup/')
        self.assertEqual(response.status_code, 404)

    def test_viewer_login_succeeds_and_gets_long_session(self):
        # The next request after login is what actually carries the
        # corrected expiry — see SessionAgeByRoleMiddleware's docstring for
        # why the login response itself can't be trusted for this.
        self.client.post(
            reverse('account_login'),
            {'login': 'viewer1', 'password': 'correct-pw-123'},
        )
        self.client.get('/')
        self.assertTrue(self.client.session.get('_auth_user_id'))
        self.assertEqual(
            self.client.session.get_expiry_age(),
            settings.NON_STAFF_SESSION_AGE,
        )

    def test_admin_login_gets_short_session_and_is_sent_to_mfa_setup(self):
        response = self.client.post(
            reverse('account_login'),
            {'login': 'admin1', 'password': 'correct-pw-123'},
            follow=True,
        )
        self.assertEqual(
            self.client.session.get_expiry_age(),
            settings.STAFF_SESSION_AGE,
        )
        # RequireAdminMFAMiddleware must redirect an unenrolled admin to
        # MFA setup instead of letting them reach the dashboard.
        self.assertRedirects(response, reverse('mfa_activate_totp'))

    def test_admin_with_totp_enrolled_is_challenged_for_a_code(self):
        # With a TOTP authenticator already enrolled, allauth's own MFA
        # stage takes over: password alone isn't enough, the user must
        # still pass the authenticate (code entry) stage before the
        # session is fully established. This is the correct two-factor
        # behavior — password + TOTP, as required by CLAUDE.md.
        Authenticator.objects.create(
            user=self.admin, type=Authenticator.Type.TOTP, data={'secret': 'test-secret'}
        )
        response = self.client.post(
            reverse('account_login'),
            {'login': 'admin1', 'password': 'correct-pw-123'},
            follow=True,
        )
        self.assertRedirects(response, reverse('mfa_authenticate'))

    def test_viewer_never_hits_mfa_gate(self):
        response = self.client.post(
            reverse('account_login'),
            {'login': 'viewer1', 'password': 'correct-pw-123'},
            follow=True,
        )
        self.assertEqual(response.redirect_chain[-1][0], '/')


@override_settings(AXES_FAILURE_LIMIT=3, AXES_COOLOFF_TIME=1, AXES_LOCKOUT_PARAMETERS=['username'])
class LoginLockoutTests(TestCase):
    """django-axes should lock out repeated failed logins for one username."""

    def setUp(self):
        User.objects.create_user(username='target', password='correct-pw-123')

    def test_lockout_after_repeated_failures(self):
        login_url = reverse('account_login')
        for _ in range(3):
            self.client.post(login_url, {'login': 'target', 'password': 'wrong'})

        response = self.client.post(login_url, {'login': 'target', 'password': 'wrong'})
        self.assertEqual(response.status_code, 429)

        # Even the correct password is now rejected until cool-off expires.
        response = self.client.post(login_url, {'login': 'target', 'password': 'correct-pw-123'})
        self.assertEqual(response.status_code, 429)
        self.assertFalse(self.client.session.get('_auth_user_id'))


class GoogleAllowlistAdapterTests(TestCase):
    """apps.accounts.adapters.AllowlistSocialAccountAdapter: Google sign-in
    only links to an existing is_staff user whose email is on the
    allow-list — never auto-creates an account. See CLAUDE.md Security."""

    def _sociallogin_for(self, email):
        from allauth.socialaccount.models import SocialLogin, SocialAccount

        user = User(email=email)
        account = SocialAccount(provider='google', uid=email)
        return SocialLogin(user=user, account=account)

    @override_settings(GOOGLE_ALLOWED_ADMIN_EMAILS=['admin@example.com'])
    def test_rejects_email_not_on_allowlist(self):
        from allauth.core.exceptions import ImmediateHttpResponse
        from apps.accounts.adapters import AllowlistSocialAccountAdapter

        sociallogin = self._sociallogin_for('nobody@example.com')
        adapter = AllowlistSocialAccountAdapter()
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(self._request(), sociallogin)

    @override_settings(GOOGLE_ALLOWED_ADMIN_EMAILS=['admin@example.com'])
    def test_rejects_allowlisted_email_with_no_matching_user(self):
        from allauth.core.exceptions import ImmediateHttpResponse
        from apps.accounts.adapters import AllowlistSocialAccountAdapter

        sociallogin = self._sociallogin_for('admin@example.com')
        adapter = AllowlistSocialAccountAdapter()
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(self._request(), sociallogin)

    @override_settings(GOOGLE_ALLOWED_ADMIN_EMAILS=['admin@example.com'])
    def test_rejects_allowlisted_email_for_non_staff_user(self):
        from allauth.core.exceptions import ImmediateHttpResponse
        from apps.accounts.adapters import AllowlistSocialAccountAdapter

        User.objects.create_user(username='nonstaff', email='admin@example.com', password='x')
        sociallogin = self._sociallogin_for('admin@example.com')
        adapter = AllowlistSocialAccountAdapter()
        with self.assertRaises(ImmediateHttpResponse):
            adapter.pre_social_login(self._request(), sociallogin)

    @override_settings(GOOGLE_ALLOWED_ADMIN_EMAILS=['admin@example.com'])
    def test_links_allowlisted_staff_user_without_error(self):
        from apps.accounts.adapters import AllowlistSocialAccountAdapter

        staff_user = User.objects.create_user(
            username='staffer', email='admin@example.com', password='x', is_staff=True
        )
        sociallogin = self._sociallogin_for('admin@example.com')
        adapter = AllowlistSocialAccountAdapter()
        adapter.pre_social_login(self._request(), sociallogin)
        self.assertEqual(sociallogin.user.pk, staff_user.pk)

    def _request(self):
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory

        request = RequestFactory().get('/accounts/login/')
        request.session = self.client.session
        setattr(request, '_messages', FallbackStorage(request))
        return request


# ════════════════════════════════════════════════════════════════════
# Roles: UserProfile, is_staff sync, and the Carpenter lockout
# ════════════════════════════════════════════════════════════════════

from decimal import Decimal

from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.converters import IntConverter

from apps.accounts.models import UserProfile

_MODEL_BACKEND = 'django.contrib.auth.backends.ModelBackend'


def _make_carpenter(username='carp1', password='correct-pw-123'):
    user = User.objects.create_user(username=username, password=password)
    user.profile.role = UserProfile.ROLE_CARPENTER
    user.profile.save()
    return user


def _make_mfa_admin(username='admin1'):
    """Admin with TOTP enrolled, so RequireAdminMFAMiddleware lets it through."""
    admin = User.objects.create_user(username=username, password='x', is_staff=True)
    Authenticator.objects.create(
        user=admin, type=Authenticator.Type.TOTP, data={'secret': 'test-secret'}
    )
    return admin


class UserProfileTests(TestCase):

    def test_profile_auto_created_from_is_staff(self):
        viewer = User.objects.create_user(username='v', password='x')
        admin = User.objects.create_user(username='a', password='x', is_staff=True)
        superuser = User.objects.create_superuser(username='s', password='x')

        self.assertEqual(viewer.profile.role, UserProfile.ROLE_VIEWER)
        self.assertEqual(admin.profile.role, UserProfile.ROLE_ADMIN)
        self.assertEqual(superuser.profile.role, UserProfile.ROLE_ADMIN)
        self.assertEqual(viewer.profile.language, 'en')

    def test_carpenter_role_forces_is_staff_off(self):
        user = User.objects.create_user(username='u', password='x', is_staff=True)
        user.profile.role = UserProfile.ROLE_CARPENTER
        user.profile.save()

        user.refresh_from_db()
        self.assertFalse(user.is_staff)
        self.assertEqual(user.profile.role, UserProfile.ROLE_CARPENTER)

    def test_admin_role_sets_is_staff(self):
        user = User.objects.create_user(username='u', password='x')
        user.profile.role = UserProfile.ROLE_ADMIN
        user.profile.save()

        user.refresh_from_db()
        self.assertTrue(user.is_staff)

    def test_is_staff_still_works_both_ways(self):
        user = _make_carpenter()

        user.is_staff = True
        user.save()
        self.assertEqual(UserProfile.objects.get(user=user).role, UserProfile.ROLE_ADMIN)

        user.is_staff = False
        user.save()
        self.assertEqual(UserProfile.objects.get(user=user).role, UserProfile.ROLE_VIEWER)

    def test_saving_non_staff_carpenter_keeps_carpenter_role(self):
        user = _make_carpenter()
        user.first_name = 'Murugan'
        user.save()
        self.assertEqual(UserProfile.objects.get(user=user).role, UserProfile.ROLE_CARPENTER)

    def test_backfill_migration_maps_is_staff(self):
        import importlib
        from django.apps import apps as global_apps

        migration = importlib.import_module('apps.accounts.migrations.0002_backfill_userprofiles')

        staff = User.objects.create_user(username='staff', password='x', is_staff=True)
        plain = User.objects.create_user(username='plain', password='x')
        UserProfile.objects.all().delete()   # simulate users that pre-date the profile table

        migration.backfill_profiles(global_apps, None)

        self.assertEqual(UserProfile.objects.get(user=staff).role, UserProfile.ROLE_ADMIN)
        self.assertEqual(UserProfile.objects.get(user=plain).role, UserProfile.ROLE_VIEWER)
        staff.refresh_from_db()
        self.assertTrue(staff.is_staff)   # User rows are not modified


def _iter_namespaced_urls(patterns, namespace=None):
    """Yields (namespace, URLPattern) for every named URL under a namespace."""
    for entry in patterns:
        if isinstance(entry, URLResolver):
            yield from _iter_namespaced_urls(entry.url_patterns, entry.namespace or namespace)
        elif isinstance(entry, URLPattern) and entry.name and namespace:
            yield namespace, entry


def _dummy_kwargs(pattern):
    converters = getattr(pattern.pattern, 'converters', {})
    return {
        name: 1 if isinstance(conv, IntConverter) else 'x'
        for name, conv in converters.items()
    }


class CarpenterLockoutTests(TestCase):
    """
    SECURITY-CRITICAL (CLAUDE.md Security rules 3 & 4): a carpenter must
    get 403 on every existing page — none of them may leak rates, costs,
    suppliers or cost sheets. The sweep walks the live URL resolver, so
    any view added later to these apps without @not_carpenter fails here.
    """

    # Every app namespace that existed before the Carpenter role. Only the
    # 'carpenter' namespace is open to carpenters.
    BLOCKED_NAMESPACES = {
        'core', 'accounts', 'products', 'resources', 'suppliers',
        'bom', 'costing', 'imports', 'quotations',
    }

    def setUp(self):
        self.carpenter = _make_carpenter()
        self.client.force_login(self.carpenter, backend=_MODEL_BACKEND)

    def _blocked_urls(self):
        urls = []
        for namespace, pattern in _iter_namespaced_urls(get_resolver().url_patterns):
            if namespace in self.BLOCKED_NAMESPACES:
                urls.append(reverse(f'{namespace}:{pattern.name}', kwargs=_dummy_kwargs(pattern)))
        return urls

    def test_every_existing_url_returns_403_for_get_and_post(self):
        urls = self._blocked_urls()
        # Guard against the sweep silently checking nothing.
        self.assertGreaterEqual(len(urls), 50)

        for url in urls:
            for method in ('get', 'post'):
                with self.subTest(url=url, method=method):
                    response = getattr(self.client, method)(url)
                    self.assertEqual(response.status_code, 403)
                    self.assertNotIn('₹', response.content.decode())

    def test_cost_bearing_pages_return_403_with_real_objects(self):
        # Same check with objects that actually exist, so a 403 can't be
        # masking what would otherwise be a 404.
        from apps.products.models import Product
        from apps.resources.models import Resource

        product = Product.objects.create(product_name='Coffee Table', product_code='COFFEE-TABLE')
        resource = Resource.objects.create(
            resource_name='Teak Wood', category='Carpentry Materials',
            unit='cft', rate=Decimal('1000'),
        )
        urls = [
            reverse('core:dashboard'),
            reverse('costing:list'),
            reverse('costing:sheet', args=[product.pk]),
            reverse('costing:export_full'),
            reverse('bom:list', args=[product.pk]),
            reverse('resources:list'),
            reverse('resources:detail', args=[resource.pk]),
            reverse('suppliers:supplier_list'),
            reverse('quotations:quotation_list'),
            reverse('quotations:product_cost_json', args=[product.pk]),
            reverse('quotations:invoice_list'),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_carpenter_cannot_reach_django_admin(self):
        response = self.client.get(reverse('admin:index'))
        self.assertNotEqual(response.status_code, 200)

    def test_carpenter_home_is_reachable(self):
        response = self.client.get(reverse('carpenter:home'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('₹', response.content.decode())

    def test_403_page_links_carpenter_home_not_dashboard(self):
        response = self.client.get(reverse('core:dashboard'))
        self.assertContains(response, reverse('carpenter:home'), status_code=403)


class CarpenterLoginRedirectTests(TestCase):

    def test_carpenter_lands_on_carpenter_home_after_login(self):
        _make_carpenter(username='carp1', password='correct-pw-123')
        response = self.client.post(
            reverse('account_login'),
            {'login': 'carp1', 'password': 'correct-pw-123'},
        )
        self.assertRedirects(response, reverse('carpenter:home'))

    def test_viewer_still_lands_on_dashboard(self):
        User.objects.create_user(username='viewer1', password='correct-pw-123')
        response = self.client.post(
            reverse('account_login'),
            {'login': 'viewer1', 'password': 'correct-pw-123'},
        )
        self.assertRedirects(response, '/')


class ViewerAccessUnchangedTests(TestCase):
    """Regression: @not_carpenter must not affect viewers."""

    def setUp(self):
        from apps.products.models import Product

        self.product = Product.objects.create(product_name='Coffee Table', product_code='COFFEE-TABLE')
        self.viewer = User.objects.create_user(username='viewer1', password='x')
        self.client.force_login(self.viewer, backend=_MODEL_BACKEND)

    def test_viewer_still_sees_read_only_pages(self):
        for url in [
            reverse('core:dashboard'),
            reverse('costing:list'),
            reverse('costing:sheet', args=[self.product.pk]),
            reverse('quotations:quotation_list'),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_viewer_cannot_reach_carpenter_home(self):
        self.assertEqual(self.client.get(reverse('carpenter:home')).status_code, 403)


class UserManagementRoleTests(TestCase):

    def setUp(self):
        self.admin = _make_mfa_admin()
        self.client.force_login(self.admin, backend=_MODEL_BACKEND)

    def test_admin_can_create_carpenter(self):
        self.client.post(reverse('accounts:user_create'), {
            'username': 'murugan', 'password': 'long-enough-pw',
            'role': 'carpenter', 'language': 'ta',
        })
        user = User.objects.get(username='murugan')
        self.assertFalse(user.is_staff)
        self.assertEqual(user.profile.role, UserProfile.ROLE_CARPENTER)
        self.assertEqual(user.profile.language, 'ta')

    def test_admin_can_change_role(self):
        other = User.objects.create_user(username='other', password='x')
        self.client.post(reverse('accounts:user_edit', args=[other.pk]), {
            'username': 'other', 'role': 'admin', 'language': 'en', 'is_active': 'on',
        })
        other.refresh_from_db()
        self.assertTrue(other.is_staff)
        self.assertEqual(other.profile.role, UserProfile.ROLE_ADMIN)

    def test_invalid_role_is_rejected(self):
        self.client.post(reverse('accounts:user_create'), {
            'username': 'x', 'password': 'long-enough-pw', 'role': 'superadmin', 'language': 'en',
        })
        self.assertFalse(User.objects.filter(username='x').exists())

    def test_admin_cannot_remove_own_admin_role(self):
        self.client.post(reverse('accounts:user_edit', args=[self.admin.pk]), {
            'username': 'admin1', 'role': 'carpenter', 'language': 'en',
        })
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)
        self.assertEqual(self.admin.profile.role, UserProfile.ROLE_ADMIN)

    def test_admin_can_edit_own_language(self):
        # Own "Active" checkbox is disabled in the form, so it's never
        # submitted — that must not be treated as self-deactivation.
        self.client.post(reverse('accounts:user_edit', args=[self.admin.pk]), {
            'username': 'admin1', 'role': 'admin', 'language': 'ta',
        })
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.profile.language, 'ta')
