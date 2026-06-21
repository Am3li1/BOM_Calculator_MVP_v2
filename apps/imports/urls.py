# apps/imports/urls.py

from django.urls import path
from . import views

app_name = 'imports'

urlpatterns = [
    path('',              views.upload,         name='upload'),
    path('result/<int:pk>/', views.import_result, name='result'),
    path('history/',      views.import_history, name='history'),
]