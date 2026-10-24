# apps/accounts/views.py
#
# Login/logout are handled by django-allauth (see config/urls.py and
# apps.accounts.adapters) — this module only keeps the admin-only User
# Management UI.

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db import transaction
from apps.core.decorators import admin_required, not_carpenter

from .models import UserProfile


_VALID_ROLES     = {code for code, _ in UserProfile.ROLE_CHOICES}
_VALID_LANGUAGES = {code for code, _ in UserProfile.LANGUAGE_CHOICES}


def _save_role(user, role, language):
    """Role is applied through UserProfile.save(), which also keeps
    user.is_staff in sync (admin ⇔ is_staff)."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.role     = role
    profile.language = language
    profile.save()


def _form_context(**extra):
    return {
        'role_choices':     UserProfile.ROLE_CHOICES,
        'language_choices': UserProfile.LANGUAGE_CHOICES,
        **extra,
    }


@login_required
@not_carpenter
@admin_required
def user_list(request):
    users = User.objects.select_related('profile').order_by('username')
    return render(request, 'accounts/user_list.html', {
        'page_title': 'User Management',
        'users': users,
    })


@login_required
@not_carpenter
@admin_required
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        role     = request.POST.get('role', UserProfile.ROLE_VIEWER)
        language = request.POST.get('language', 'en')

        if not username or not password:
            messages.error(request, 'Username and password are required.')
        elif role not in _VALID_ROLES or language not in _VALID_LANGUAGES:
            messages.error(request, 'Invalid role or language.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        else:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username,
                    password=password,
                    is_staff=(role == UserProfile.ROLE_ADMIN),
                )
                _save_role(user, role, language)
            messages.success(request, f'User "{user.username}" created successfully.')
            return redirect('accounts:user_list')

    return render(request, 'accounts/user_form.html', _form_context(
        page_title='Add User',
        form_action='Create User',
    ))


@login_required
@not_carpenter
@admin_required
def user_edit(request, pk):
    edited_user = User.objects.get(pk=pk)

    if request.method == 'POST':
        is_self   = edited_user == request.user
        username  = request.POST.get('username', '').strip()
        role      = request.POST.get('role', UserProfile.ROLE_VIEWER)
        language  = request.POST.get('language', 'en')
        # The Active checkbox is rendered disabled on your own account, and
        # disabled inputs aren't submitted — so your own account is always
        # kept active rather than read from the form.
        is_active = True if is_self else request.POST.get('is_active') == 'on'

        if not username:
            messages.error(request, 'Username is required.')
        elif role not in _VALID_ROLES or language not in _VALID_LANGUAGES:
            messages.error(request, 'Invalid role or language.')
        elif is_self and role != UserProfile.ROLE_ADMIN:
            # Prevent admins from locking themselves out
            messages.error(request, 'You cannot remove your own Admin role.')
        elif User.objects.filter(username=username).exclude(pk=pk).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        else:
            with transaction.atomic():
                edited_user.username  = username
                edited_user.is_staff  = role == UserProfile.ROLE_ADMIN
                edited_user.is_active = is_active
                edited_user.save()
                _save_role(edited_user, role, language)
            messages.success(request, f'User "{edited_user.username}" updated.')
            return redirect('accounts:user_list')

    profile, _ = UserProfile.objects.get_or_create(user=edited_user)
    return render(request, 'accounts/user_form.html', _form_context(
        page_title=f'Edit User — {edited_user.username}',
        form_action='Save Changes',
        edited_user=edited_user,
        current_role=profile.role,
        current_language=profile.language,
    ))


@login_required
@not_carpenter
@admin_required
def user_change_password(request, pk):
    edited_user = User.objects.get(pk=pk)

    if request.method == 'POST':
        password  = request.POST.get('password', '').strip()
        password2 = request.POST.get('password2', '').strip()

        if not password:
            messages.error(request, 'Password cannot be empty.')
        elif password != password2:
            messages.error(request, 'Passwords do not match.')
        elif len(password) < 8:
            messages.error(request, 'Password must be at least 8 characters.')
        else:
            edited_user.set_password(password)
            edited_user.save()
            messages.success(
                request,
                f'Password changed for "{edited_user.username}".'
            )
            return redirect('accounts:user_list')

    return render(request, 'accounts/user_password_form.html', {
        'page_title': f'Change Password — {edited_user.username}',
        'edited_user': edited_user,
    })