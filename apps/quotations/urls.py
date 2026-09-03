# apps/quotations/urls.py
from django.urls import path
from . import views

app_name = 'quotations'

urlpatterns = [
    path('', views.quotation_list, name='quotation_list'),
    path('create/', views.quotation_create, name='quotation_create'),
    path('<int:pk>/', views.quotation_detail, name='quotation_detail'),
    path('<int:pk>/pdf/', views.quotation_pdf, name='quotation_pdf'),
    path('<int:pk>/status/', views.quotation_update_status, name='quotation_update_status'),

    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/search.json', views.customer_search_json, name='customer_search_json'),

    path('products/<int:pk>/cost.json', views.product_cost_json, name='product_cost_json'),

    path('<int:pk>/edit/', views.quotation_edit, name='quotation_edit'),
path('<int:pk>/delete/', views.quotation_delete, name='quotation_delete'),
]