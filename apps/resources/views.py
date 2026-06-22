# apps/resources/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q

from .models import Resource, ResourceCategory
from .forms import ResourceForm


@login_required
def resource_list(request):
    """
    Shows all resources in a searchable, filterable table.
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

    # ── Categories from database (not hardcoded) ────────────────────
    # We show ALL distinct categories currently in use,
    # plus any active ResourceCategory records.
    # This way even imported categories that aren't in
    # ResourceCategory yet still appear in the filter.
    db_categories = ResourceCategory.objects.filter(
        active=True
    ).values_list('name', flat=True)

    # Also catch any categories from imports not yet in ResourceCategory
    import_categories = Resource.objects.values_list(
        'category', flat=True
    ).distinct()

    # Merge and deduplicate, sorted alphabetically
    all_categories = sorted(set(
        list(db_categories) + [c for c in import_categories if c]
    ))

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
    GET  → shows blank form with database categories
    POST → validates and saves new resource
    """
    # Fetch categories from database for the dropdown
    categories = ResourceCategory.objects.filter(
        active=True
    ).order_by('sort_order', 'name')

    if request.method == 'POST':
        form = ResourceForm(request.POST, categories=categories)
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
        form = ResourceForm(categories=categories)

    return render(request, 'resources/form.html', {
        'page_title': 'Add Resource',
        'form': form,
        'form_title': 'Add New Resource',
        'submit_label': 'Create Resource',
        'categories': categories,
    })


@login_required
def resource_edit(request, pk):
    """
    GET  → shows form pre-filled with existing data
    POST → validates and saves changes
    """
    resource = get_object_or_404(Resource, pk=pk)

    categories = ResourceCategory.objects.filter(
        active=True
    ).order_by('sort_order', 'name')

    if request.method == 'POST':
        form = ResourceForm(
            request.POST,
            instance=resource,
            categories=categories
        )
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
        form = ResourceForm(instance=resource, categories=categories)

    return render(request, 'resources/form.html', {
        'page_title': f'Edit — {resource.resource_name}',
        'form': form,
        'form_title': f'Edit Resource: {resource.resource_name}',
        'submit_label': 'Save Changes',
        'resource': resource,
        'categories': categories,
    })


@login_required
def resource_toggle_active(request, pk):
    """
    Toggles a resource between active and inactive.
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

@login_required
def resource_delete(request, pk):
    """
    Deletes a resource only if it is not used in any BOM or Dimension entry.

    If the resource IS in use:
        - Show a clear error explaining which products use it
        - Offer to deactivate instead (hides it without breaking data)

    If the resource is NOT in use:
        - Confirm via POST and delete permanently
    """
    from apps.bom.models import BOMItem, WoodPart

    resource = get_object_or_404(Resource, pk=pk)

    # Check if this resource is referenced anywhere
    bom_count  = BOMItem.objects.filter(resource=resource).count()
    wood_count = WoodPart.objects.filter(resource=resource).count()
    in_use     = bom_count > 0 or wood_count > 0

    if request.method == 'POST':
        if in_use:
            # User confirmed deactivation instead
            action = request.POST.get('action')
            if action == 'deactivate':
                resource.active = False
                resource.save()
                messages.success(
                    request,
                    f'"{resource.resource_name}" has been deactivated. '
                    f'It will no longer appear in BOM dropdowns.'
                )
                return redirect('resources:list')
            else:
                messages.error(
                    request,
                    f'Cannot delete "{resource.resource_name}" '
                    f'because it is used in {bom_count} BOM item(s) '
                    f'and {wood_count} dimension entry/entries. '
                    f'Deactivate it instead to hide it from dropdowns.'
                )
                return redirect('resources:list')
        else:
            # Safe to delete — not used anywhere
            name = resource.resource_name
            resource.delete()
            messages.success(
                request,
                f'Resource "{name}" has been permanently deleted.'
            )
            return redirect('resources:list')

    # GET request — show confirmation page
    context = {
        'page_title': f'Delete — {resource.resource_name}',
        'resource':   resource,
        'bom_count':  bom_count,
        'wood_count': wood_count,
        'in_use':     in_use,
    }
    return render(request, 'resources/delete.html', context)