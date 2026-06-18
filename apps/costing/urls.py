from django.urls import path
from . import views

app_name = 'costing'
urlpatterns = [
    path('', views.costing_list, name='list'),
]