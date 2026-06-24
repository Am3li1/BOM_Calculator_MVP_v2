# apps/suppliers/urls.py  — FINAL FILE
from django.urls import path
from . import views

app_name = 'suppliers'

urlpatterns = [
    path('', views.supplier_list, name='supplier_list'),

    # NEW: Supplier detail page — /suppliers/5/
    # <int:pk> captures the supplier's primary key from the URL.
    # 'supplier_detail' is the name used in {% url 'suppliers:supplier_detail' pk %}
    path('<int:pk>/', views.supplier_detail, name='supplier_detail'),
    path('create/', views.supplier_create, name='supplier_create'),
    path('<int:pk>/edit/', views.supplier_edit, name='supplier_edit'),
    path('<int:pk>/toggle/', views.supplier_toggle_active, name='supplier_toggle_active'),
]