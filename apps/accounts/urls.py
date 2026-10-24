# apps/accounts/urls.py
#
# Login/logout live outside this namespace — see config/urls.py
# ('account_login' / 'account_logout', provided by django-allauth).

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # User management (admin only)
    path('users/',                        views.user_list,            name='user_list'),
    path('users/create/',                 views.user_create,          name='user_create'),
    path('users/<int:pk>/edit/',          views.user_edit,            name='user_edit'),
    path('users/<int:pk>/password/',      views.user_change_password, name='user_change_password'),
]