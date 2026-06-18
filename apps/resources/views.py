# apps/resources/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q

from .models import Resource
from .forms import ResourceForm


@login_required
def resource_list(request):
    """
    Shows all resources in a searchable, filterable table.
    Supports:
        - Text search by name
        - Filter by category
        - Filter by active/inactive
    """
    resources = Resource.objects.all()

    # ── Search ──────────────────────────────────────────────────────
    search_query = request.GET.get('search', '').strip()
    if search_query:
        resources = resources.filter(
            Q(resource_name__icontains=search_query) |
            Q(category__icontains=search_query) |
            Q(unit__icontains=search_query)
        )

    # ── Filter by Category ──────────────────────────────────────────
    category_filter = request.GET.get('category', '')
    if category_filter:
        resources = resources.filter(category=category_filter)

    # ── Filter by Status ────────────────────────────────────────────
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        resources = resources.filter(active=True)
    elif status_filter == 'inactive':
        resources = resources.filter(active=False)

    # ── All categories for filter dropdown ──────────────────────────
    all_categories = Resource.CATEGORY_CHOICES

    context = {
        'page_title': 'Resources',
        'resources': resources,
        'search_query': search_query,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'all_categories': all_categories,
        'total_count': resources.count(),
    }
    return render(request, 'resources/list.html', context)


@login_required
def resource_create(request):
    """
    GET  → shows blank form
    POST → validates and saves new resource
    """
    if request.method == 'POST':
        form = ResourceForm(request.POST)
        if form.is_valid():
            resource = form.save()
            messages.success(
                request,
                f'Resource "{resource.resource_name}" created successfully.'
            )
            return redirect('resources:list')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = ResourceForm()

    return render(request, 'resources/form.html', {
        'page_title': 'Add Resource',
        'form': form,
        'form_title': 'Add New Resource',
        'submit_label': 'Create Resource',
    })


@login_required
def resource_edit(request, pk):
    """
    GET  → shows form pre-filled with existing data
    POST → validates and saves changes
    
    pk = primary key (the id of the resource to edit)
    get_object_or_404 → returns 404 page if resource not found
    """
    resource = get_object_or_404(Resource, pk=pk)

    if request.method == 'POST':
        # instance=resource tells the form to UPDATE this row, not create new
        form = ResourceForm(request.POST, instance=resource)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Resource "{resource.resource_name}" updated successfully.'
            )
            return redirect('resources:list')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = ResourceForm(instance=resource)

    return render(request, 'resources/form.html', {
        'page_title': f'Edit — {resource.resource_name}',
        'form': form,
        'form_title': f'Edit Resource: {resource.resource_name}',
        'submit_label': 'Save Changes',
        'resource': resource,
    })


@login_required
def resource_toggle_active(request, pk):
    """
    Toggles a resource between active and inactive.
    We never hard-delete resources — they may be used in BOMs.
    Only responds to POST requests for security.
    """
    resource = get_object_or_404(Resource, pk=pk)

    if request.method == 'POST':
        resource.active = not resource.active
        resource.save()
        status = 'activated' if resource.active else 'deactivated'
        messages.success(
            request,
            f'Resource "{resource.resource_name}" {status}.'
        )

    return redirect('resources:list')