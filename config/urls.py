# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # Our apps
    path('', include('apps.core.urls')),            # dashboard at /
    path('accounts/', include('apps.accounts.urls')), # login/logout
    path('products/', include('apps.products.urls')),
    path('resources/', include('apps.resources.urls')),
    path('bom/', include('apps.bom.urls')),
    path('imports/', include('apps.imports.urls')),
    path('costing/', include('apps.costing.urls')),
]

# Serve uploaded files (Excel files) during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)