# apps/accounts/views.py

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages


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