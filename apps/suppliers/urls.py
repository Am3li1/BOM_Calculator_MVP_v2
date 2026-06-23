# apps/suppliers/urls.py

from django.urls import path
from . import views

app_name = 'suppliers'

urlpatterns = [
    path('',                    views.supplier_list,          name='list'),
    path('create/',             views.supplier_create,        name='create'),
    path('<int:pk>/edit/',      views.supplier_edit,          name='edit'),
    path('<int:pk>/toggle/',    views.supplier_toggle_active, name='toggle'),
]