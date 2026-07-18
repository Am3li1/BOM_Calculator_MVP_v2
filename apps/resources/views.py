# apps/resources/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from apps.core.decorators import admin_required
from django.contrib import messages
from django.db.models import Q

from .models import Resource, ResourceCategory
from .forms import ResourceForm
from decimal import Decimal


@login_required
@admin_required
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

    # ── Filter by Status ─────────────────────────────────────────────
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        resources = resources.filter(active=True)
    elif status_filter == 'inactive':
        resources = resources.filter(active=False)

    # ── Sort ─────────────────────────────────────────────────────────
    # No 'sort' param = default DB ordering (Resource.Meta.ordering,
    # i.e. category then name). ?sort=name_asc / name_desc switches to
    # a flat, letters-first alphabetical sort by resource_name —
    # digit/symbol-led names (e.g. "10 mm Stapler") sort after letters,
    # matching the same rule used for the Category dropdown.
    sort = request.GET.get('sort', '')

    if sort in ('name_asc', 'name_desc'):
        resources = list(resources)

        def _sort_key(resource):
            first_char = resource.resource_name.strip()[:1]
            return (
                (0, resource.resource_name.lower())
                if first_char.isalpha()
                else (1, resource.resource_name.lower())
            )

        resources.sort(key=_sort_key, reverse=(sort == 'name_desc'))

    next_sort = 'name_desc' if sort == 'name_asc' else 'name_asc'

    # ── Categories from database (not hardcoded) ─────────────────────
    all_categories = ResourceCategory.get_available_names()

    paginator = Paginator(resources, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    context = {
        'page_title': 'Resources',
        'resources': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'all_categories': all_categories,
        'total_count': len(resources) if isinstance(resources, list) else resources.count(),
        'sort': sort,
        'next_sort': next_sort,
    }
    return render(request, 'resources/list.html', context)


@login_required
@admin_required
def resource_create(request):
    """
    GET  → shows blank form with database categories
    POST → validates and saves new resource
    """
    # Fetch categories from database for the dropdown
    # Categories for the dropdown — same merged source as the
    # Resources list filter (active ResourceCategory rows + any
    # category already in use on a Resource). The old version only
    # queried ResourceCategory, so the dropdown could be empty even
    # when 100+ resources already had real categories.
    categories = ResourceCategory.get_available_names()

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
@admin_required
def resource_edit(request, pk):
    """
    GET  → shows form pre-filled with existing data
    POST → validates and saves changes
    """
    resource = get_object_or_404(Resource, pk=pk)

    categories = ResourceCategory.get_available_names()

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
@admin_required
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
@admin_required
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

@login_required
@admin_required
def resource_detail(request, pk):
    from apps.suppliers.models import Supplier, ResourceSupplier
    from decimal import Decimal

    resource = get_object_or_404(Resource, pk=pk)

    linked_suppliers = ResourceSupplier.objects.filter(
        resource=resource
    ).select_related('supplier').order_by('-preferred', 'supplier_rate')

    linked_supplier_ids = linked_suppliers.values_list(
        'supplier_id', flat=True
    )
    available_suppliers = Supplier.objects.filter(
        active=True
    ).exclude(id__in=linked_supplier_ids)

    # Price comparison data
    active_links      = linked_suppliers.filter(active=True)
    cheapest_rate     = Decimal('0')
    highest_rate      = Decimal('0')
    rate_saving       = Decimal('0')
    cheapest_supplier = ''
    cheapest_link     = None

    if active_links.count() > 1:
        cheapest_link     = active_links.order_by('supplier_rate').first()
        most_expensive    = active_links.order_by('-supplier_rate').first()
        cheapest_rate     = cheapest_link.supplier_rate
        highest_rate      = most_expensive.supplier_rate
        rate_saving       = highest_rate - cheapest_rate
        cheapest_supplier = cheapest_link.supplier.supplier_name

    context = {
        'page_title':          resource.resource_name,
        'resource':            resource,
        'linked_suppliers':    linked_suppliers,
        'available_suppliers': available_suppliers,
        'cheapest_rate':       cheapest_rate,
        'highest_rate':        highest_rate,
        'rate_saving':         rate_saving,
        'cheapest_supplier':   cheapest_supplier,
        'cheapest_link':       cheapest_link,
    }
    return render(request, 'resources/detail.html', context)

@login_required
@admin_required
def resource_set_override(request, pk):
    """
    Sets or clears the manual override rate on a resource.

    POST with a rate value → sets the override
    POST with blank rate   → clears the override
                             (reverts to automatic supplier pricing)
    """
    resource = get_object_or_404(Resource, pk=pk)

    if request.method == 'POST':
        override_rate   = request.POST.get('manual_override_rate', '').strip()
        override_reason = request.POST.get('override_reason', '').strip()

        if override_rate == '':
            # User cleared the field — revert to automatic pricing
            resource.manual_override_rate = None
            resource.override_reason      = ''
            resource.save()
            messages.success(
                request,
                f'Override removed for "{resource.resource_name}". '
                f'Rate will now be determined automatically from '
                f'supplier pricing.'
            )
        else:
            try:
                rate = Decimal(override_rate)
                if rate < 0:
                    raise ValueError()
                resource.manual_override_rate = rate
                resource.override_reason      = override_reason
                resource.save()
                messages.success(
                    request,
                    f'Override rate ₹{rate} set for '
                    f'"{resource.resource_name}". '
                    f'All costing will use this rate.'
                )
            except (ValueError, Exception):
                messages.error(
                    request,
                    'Invalid rate. Please enter a positive number '
                    'or leave blank to clear the override.'
                )

    return redirect('resources:detail', pk=pk)