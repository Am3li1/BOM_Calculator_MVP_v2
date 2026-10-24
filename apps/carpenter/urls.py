# apps/carpenter/urls.py

from django.urls import path
from . import views

app_name = 'carpenter'

urlpatterns = [
    path('', views.home, name='home'),
]
