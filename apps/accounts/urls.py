# apps/accounts/urls.py

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/',  views.login_view,  name='login'),
    path('logout/', views.logout_view, name='logout'),

    # User management (admin only)
    path('users/',                        views.user_list,            name='user_list'),
    path('users/create/',                 views.user_create,          name='user_create'),
    path('users/<int:pk>/edit/',          views.user_edit,            name='user_edit'),
    path('users/<int:pk>/password/',      views.user_change_password, name='user_change_password'),
]