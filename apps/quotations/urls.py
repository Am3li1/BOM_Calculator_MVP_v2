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
    path('<int:pk>/edit/', views.quotation_edit, name='quotation_edit'),
    path('<int:pk>/delete/', views.quotation_delete, name='quotation_delete'),
    path('<int:pk>/convert-to-invoice/', views.quotation_convert_to_invoice, name='quotation_convert_to_invoice'),

    path('customers/', views.customer_list, name='customer_list'),
    path('customers/create/', views.customer_create, name='customer_create'),
    path('customers/search.json', views.customer_search_json, name='customer_search_json'),

    path('products/<int:pk>/cost.json', views.product_cost_json, name='product_cost_json'),

    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/<int:pk>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<int:pk>/edit/', views.invoice_edit, name='invoice_edit'),
    path('invoices/<int:pk>/finalize/', views.invoice_finalize, name='invoice_finalize'),
    path('invoices/<int:pk>/delete/', views.invoice_delete, name='invoice_delete'),
    path('invoices/<int:pk>/pdf/', views.invoice_pdf, name='invoice_pdf'),
]