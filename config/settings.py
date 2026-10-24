# config/settings.py

from pathlib import Path
from decouple import config, Csv
import dj_database_url

# ── Base Directory ───────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent


# ── Security ─────────────────────────────────────────────────────────
# SECRET_KEY comes from environment variable — never hardcoded
SECRET_KEY = config('SECRET_KEY')

# DEBUG comes from environment variable
# Locally: DEBUG=True (in .env)
# On Render: DEBUG=False (set in Render dashboard)
DEBUG = config('DEBUG', default=False, cast=bool)

# ALLOWED_HOSTS comes from environment variable
# Locally: localhost,127.0.0.1
# On Render: your-app.onrender.com
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost', cast=Csv())
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

# Non-default Django admin path — reduces automated-scanner noise against
# the well-known /admin/ path. Not a security boundary by itself (auth is
# still the real gate), just one less obvious target. Must end with '/'.
DJANGO_ADMIN_URL = config('DJANGO_ADMIN_URL', default='django-admin/')


# ── Application Definition ───────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',  # required by allauth

    # Third-party utilities
    'django_extensions',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.mfa',
    'axes',

    # Your apps
    'apps.core',
    'apps.accounts',
    'apps.products',
    'apps.resources',
    'apps.bom',
    'apps.costing',
    'apps.imports',
    'apps.suppliers',
    'apps.quotations',
    'apps.carpenter',
]

SITE_ID = 1

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise must be directly after SecurityMiddleware
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'apps.accounts.middleware.SessionAgeByRoleMiddleware',
    # Must come after MessageMiddleware — it uses the messages framework.
    'apps.accounts.middleware.RequireAdminMFAMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # django-axes must be last so it sees the final response of every
    # other middleware before deciding whether a login attempt counts.
    'axes.middleware.AxesMiddleware',
]

AUTHENTICATION_BACKENDS = [
    # Must come first — lets axes block a login attempt before it reaches
    # the real backends.
    'axes.backends.AxesBackend',
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.user_role',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ── Database ──────────────────────────────────────────────────────────
DATABASE_URL = config("DATABASE_URL", default=None)

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
        )
    }
else:
    SQLITE_PATH = config(
        "SQLITE_PATH",
        default=str(BASE_DIR / "db.sqlite3"),
    )

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": SQLITE_PATH,
        }
    }

# ── Password Validation ───────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# ── Internationalisation ──────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE     = 'Asia/Kolkata'
USE_I18N      = True
USE_TZ        = True


# ── Static Files ──────────────────────────────────────────────────────
# WhiteNoise serves static files in production without Nginx
STATIC_URL  = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise compression and caching
STATICFILES_STORAGE = (
    'whitenoise.storage.CompressedManifestStaticFilesStorage'
)

# If you have a /static/ folder with your own CSS/JS/images
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]


# ── Media Files ───────────────────────────────────────────────────────
MEDIA_URL  = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ── Authentication ────────────────────────────────────────────────────
LOGIN_URL          = 'account_login'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = 'account_login'

# ── Session lifetime by role ────────────────────────────────────────────
# Django only has one global SESSION_COOKIE_AGE; apps.accounts.signals
# overrides it per-session on login based on is_staff. STAFF_SESSION_AGE
# is also the value Django uses before that signal runs (e.g. admin login
# via Django's own admin site).
STAFF_SESSION_AGE     = 60 * 60 * 8        # 8 hours — admins/staff
NON_STAFF_SESSION_AGE = 60 * 60 * 24 * 30  # 30 days — viewers / carpenters
SESSION_COOKIE_AGE = STAFF_SESSION_AGE

# ── django-allauth ───────────────────────────────────────────────────────
ACCOUNT_ADAPTER = 'apps.accounts.adapters.NoSignupAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapters.AllowlistSocialAccountAdapter'

# Username/password only — no email-based login, no self-signup. Accounts
# are created by an admin via the existing User Management UI.
ACCOUNT_LOGIN_METHODS = {'username'}
ACCOUNT_SIGNUP_FIELDS = ['username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_LOGOUT_ON_GET = False
ACCOUNT_LOGOUT_REDIRECT_URL = LOGOUT_REDIRECT_URL

# Google sign-in: provider app config comes entirely from env vars (no
# SocialApp row needed in the DB). Who may actually use it is gated by
# apps.accounts.adapters.AllowlistSocialAccountAdapter against this list —
# only existing is_staff accounts whose email is on the allow-list may
# link/sign in with Google; nothing is auto-created.
GOOGLE_ALLOWED_ADMIN_EMAILS = config('GOOGLE_ALLOWED_ADMIN_EMAILS', default='', cast=Csv())
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': config('GOOGLE_OAUTH_CLIENT_ID', default=''),
            'secret': config('GOOGLE_OAUTH_CLIENT_SECRET', default=''),
            'key': '',
        },
        'SCOPE': ['profile', 'email'],
        'OAUTH_PKCE_ENABLED': True,
    }
}

# MFA (TOTP) — enforced for every is_staff account by
# apps.accounts.middleware.RequireAdminMFAMiddleware, since allauth itself
# only makes MFA available, not mandatory.
MFA_SUPPORTED_TYPES = ['totp', 'recovery_codes']
MFA_TOTP_ISSUER = config('MFA_TOTP_ISSUER', default='BOM Costing')

# ── django-axes (login lockout) ─────────────────────────────────────────
AXES_FAILURE_LIMIT = config('AXES_FAILURE_LIMIT', default=5, cast=int)
AXES_COOLOFF_TIME = config('AXES_COOLOFF_TIME_HOURS', default=1, cast=int)
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']
AXES_RESET_ON_SUCCESS = True

# ── Proxy / HTTPS (behind Traefik, which terminates TLS) ────────────────
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=not DEBUG, cast=bool)

SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0 if DEBUG else 31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=True, cast=bool)

# ── Cookies ──────────────────────────────────────────────────────────────
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=bool)
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'


# ── Default Primary Key ───────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ── Messages ──────────────────────────────────────────────────────────
from django.contrib.messages import constants as messages
MESSAGE_TAGS = {
    messages.ERROR: 'danger',
}

# ── Logging ──────────────────────────────────────────────────────────
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

EXTERNAL_API_KEY = config('EXTERNAL_API_KEY')  # shared secret — Elite's system authenticates with this