# apps/carpenter/urls.py

from django.urls import path
from . import views

app_name = 'carpenter'

urlpatterns = [
    path('', views.home, name='home'),
    # Public magic link — no login. See views.link_form.
    path('link/<str:token>/', views.link_form, name='link_form'),
]
