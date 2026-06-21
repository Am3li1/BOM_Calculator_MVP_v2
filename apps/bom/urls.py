from django.urls import path
from . import views

app_name = 'bom'

urlpatterns = [
    # Standard BOM
    path('<int:product_pk>/',        views.bom_list,          name='list'),
    path('<int:product_pk>/add/',    views.bom_add,           name='add'),
    path('item/<int:pk>/remove/',    views.bom_remove,        name='remove'),
    path('item/<int:pk>/edit-qty/',  views.bom_edit_quantity, name='edit_qty'),

    # Wood Parts
    path('<int:product_pk>/wood/add/',      views.woodpart_add,    name='wood_add'),
    path('wood/<int:pk>/remove/',           views.woodpart_remove, name='wood_remove'),
]