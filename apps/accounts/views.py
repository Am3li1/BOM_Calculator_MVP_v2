# apps/accounts/views.py

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from apps.core.decorators import admin_required

def login_view(request):
    """
    Handles user login.
    GET  → shows the login form
    POST → validates credentials and logs in
    """
    # If already logged in, send to dashboard
    if request.user.is_authenticated:
        return redirect('core:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            # Go to the page they were trying to reach, or dashboard
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password. Please try again.')

    return render(request, 'accounts/login.html')


def logout_view(request):
    """Logs the user out and redirects to login page."""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('accounts:login')

@login_required
@admin_required
def user_list(request):
    users = User.objects.all().order_by('username')
    return render(request, 'accounts/user_list.html', {
        'page_title': 'User Management',
        'users': users,
    })


@login_required
@admin_required
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        is_staff = request.POST.get('is_staff') == 'on'

        if not username or not password:
            messages.error(request, 'Username and password are required.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                is_staff=is_staff,
            )
            messages.success(request, f'User "{user.username}" created successfully.')
            return redirect('accounts:user_list')

    return render(request, 'accounts/user_form.html', {
        'page_title': 'Add User',
        'form_action': 'Create User',
    })


@login_required
@admin_required
def user_edit(request, pk):
    edited_user = User.objects.get(pk=pk)

    # Prevent admins from locking themselves out
    if edited_user == request.user and not request.POST.get('is_active'):
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('accounts:user_list')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active') == 'on'

        if not username:
            messages.error(request, 'Username is required.')
        elif User.objects.filter(username=username).exclude(pk=pk).exists():
            messages.error(request, f'Username "{username}" is already taken.')
        else:
            edited_user.username  = username
            edited_user.is_staff  = is_staff
            edited_user.is_active = is_active
            edited_user.save()
            messages.success(request, f'User "{edited_user.username}" updated.')
            return redirect('accounts:user_list')

    return render(request, 'accounts/user_form.html', {
        'page_title': f'Edit User — {edited_user.username}',
        'form_action': 'Save Changes',
        'edited_user': edited_user,
    })


@login_required
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