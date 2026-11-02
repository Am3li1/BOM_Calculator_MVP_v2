# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from allauth.account.views import LoginView, LogoutView

from apps.products import api as products_api

urlpatterns = [
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),

    # Auth — django-allauth. Mounted individually (not via allauth.urls)
    # so we never expose allauth's own signup/password-reset URLs; those
    # flows are intentionally closed — see CLAUDE.md Authentication section.
    path('accounts/login/', LoginView.as_view(), name='account_login'),
    path('accounts/logout/', LogoutView.as_view(), name='account_logout'),
    path('accounts/3rdparty/', include('allauth.socialaccount.urls')),
    path('accounts/google/', include('allauth.socialaccount.providers.google.urls')),

    # Our apps
    path('', include('apps.core.urls')),            # dashboard at /
    path('accounts/', include('apps.accounts.urls')), # user management
    path('products/', include('apps.products.urls')),
    path('resources/', include('apps.resources.urls')),
    path('bom/', include('apps.bom.urls')),
    path('imports/', include('apps.imports.urls')),
    path('costing/', include('apps.costing.urls')),
    path('suppliers/', include('apps.suppliers.urls')),
    path('quotations/', include('apps.quotations.urls')),
    path('carpenter/', include('apps.carpenter.urls')),
    # Cross-system API — read-only, shared-secret auth, called by the
    # separate Elite Furniture Mart project over Tailscale (see
    # apps/products/api.py for details).
    path('api/products/<str:product_code>/cost/', products_api.product_cost_api, name='product_cost_api'),
]

# Serve uploaded files (Excel files) during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)