# apps/resources/urls.py

from django.urls import path
from . import views

app_name = 'resources'

urlpatterns = [
    path('', views.resource_list, name='list'),
    path('create/', views.resource_create, name='create'),
    path('<int:pk>/edit/', views.resource_edit, name='edit'),
    path('<int:pk>/toggle/', views.resource_toggle_active, name='toggle'),
]