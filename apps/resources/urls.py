# apps/resources/urls.py

from django.urls import path
from . import views
from apps.suppliers import views as supplier_views

app_name = 'resources'

urlpatterns = [
    path('',
         views.resource_list,
         name='list'),

    path('create/',
         views.resource_create,
         name='create'),

    path('<int:pk>/edit/',
         views.resource_edit,
         name='edit'),

    path('<int:pk>/toggle/',
         views.resource_toggle_active,
         name='toggle'),

    path('<int:pk>/delete/',
         views.resource_delete,
         name='delete'),

    path('<int:pk>/',
         views.resource_detail,
         name='detail'),

    path('<int:resource_pk>/suppliers/link/',
         supplier_views.resource_link_supplier,
         name='link_supplier'),

    path('<int:resource_pk>/suppliers/<int:supplier_pk>/unlink/',
         supplier_views.resource_unlink_supplier,
         name='unlink_supplier'),

    path('<int:resource_pk>/suppliers/<int:supplier_pk>/set-preferred/',
         supplier_views.resource_set_preferred,
         name='set_preferred'),

    path('<int:resource_pk>/suppliers/<int:supplier_pk>/update-rate/',
         supplier_views.resource_update_supplier_rate,
         name='update_supplier_rate'),

     path('<int:pk>/set-override/',
          views.resource_set_override,
          name='set_override'),
]