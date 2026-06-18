from django.urls import path
from . import views

app_name = 'bom'
urlpatterns = [
    path('', views.bom_list, name='list'),
]