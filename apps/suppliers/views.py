# apps/suppliers/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.db import transaction

from .models import Supplier, ResourceSupplier
from .forms import SupplierForm
from decimal import Decimal

# ── Supplier CRUD ─────────────────────────────────────────────────────

@login_required
def supplier_list(request):
    search_query = request.GET.get('search', '').strip()
    suppliers = Supplier.objects.all()

    if search_query:
        suppliers = suppliers.filter(
            Q(supplier_name__icontains=search_query) |
            Q(phone_number__icontains=search_query) |
            Q(gst_number__icontains=search_query)
        )

    paginator = Paginator(suppliers, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))
    
    context = {
        'page_title': 'Suppliers',
        'suppliers': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'total_count': suppliers.count(),
    }
    return render(request, 'suppliers/list.html', context)


@login_required
def supplier_create(request):
    if request.method == 'POST':
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            messages.success(
                request,
                f'Supplier "{supplier.supplier_name}" created.'
            )
            next_url = request.POST.get('next')
            return redirect(next_url if next_url else 'suppliers:supplier_list')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = SupplierForm()

    return render(request, 'suppliers/form.html', {
        'page_title': 'Add Supplier',
        'form': form,
        'form_title': 'Add New Supplier',
        'submit_label': 'Create Supplier',
    })


@login_required
def supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)

    if request.method == 'POST':
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Supplier "{supplier.supplier_name}" updated.'
            )
            return redirect('suppliers:supplier_list')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = SupplierForm(instance=supplier)

    return render(request, 'suppliers/form.html', {
        'page_title': f'Edit — {supplier.supplier_name}',
        'form': form,
        'form_title': f'Edit: {supplier.supplier_name}',
        'submit_label': 'Save Changes',
        'supplier': supplier,
    })


@login_required
def supplier_toggle_active(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == 'POST':
        supplier.active = not supplier.active
        supplier.save()
        status = 'activated' if supplier.active else 'deactivated'
        messages.success(
            request,
            f'"{supplier.supplier_name}" {status}.'
        )
    next_url = request.POST.get('next')
    return redirect(next_url if next_url else 'suppliers:supplier_list')


# ── Resource-Supplier linking ─────────────────────────────────────────

@login_required
def resource_link_supplier(request, resource_pk):
    """
    Links a supplier to a resource with a rate.
    If this is the first supplier being linked,
    automatically marks it as preferred.
    """
    from apps.resources.models import Resource

    resource = get_object_or_404(Resource, pk=resource_pk)

    if request.method == 'POST':
        supplier_id  = request.POST.get('supplier_id')
        supplier_rate = request.POST.get('supplier_rate', '0').strip()

        if not supplier_id:
            messages.error(request, 'Please select a supplier.')
            return redirect('resources:detail', pk=resource_pk)

        try:
            rate = float(supplier_rate)
            if rate < 0:
                raise ValueError()
        except (TypeError, ValueError):
            messages.error(
                request,
                'Please enter a valid rate (0 or more).'
            )
            return redirect('resources:detail', pk=resource_pk)

        supplier = get_object_or_404(
            Supplier, pk=supplier_id, active=True
        )

        # Check if this is the first supplier being linked
        # If so, automatically mark it as preferred
        is_first = not ResourceSupplier.objects.filter(
            resource=resource, active=True
        ).exists()

        link, created = ResourceSupplier.objects.get_or_create(
            resource=resource,
            supplier=supplier,
            defaults={
                'supplier_rate': rate,
                'preferred': is_first,
                'active': True,
            }
        )

        if not created:
            # Link already exists — update the rate
            link.supplier_rate = rate
            link.active = True
            link.save()
            messages.info(
                request,
                f'Rate for "{supplier.supplier_name}" updated '
                f'to ₹{rate}.'
            )
        else:
            preferred_msg = ' (set as preferred — first supplier)' \
                if is_first else ''
            messages.success(
                request,
                f'"{supplier.supplier_name}" linked at '
                f'₹{rate}{preferred_msg}.'
            )

    return redirect('resources:detail', pk=resource_pk)


@login_required
def resource_unlink_supplier(request, resource_pk, supplier_pk):
    """
    Removes a supplier link. If it was the preferred supplier,
    automatically promotes the cheapest remaining supplier.
    """
    from apps.resources.models import Resource

    resource = get_object_or_404(Resource, pk=resource_pk)
    link = get_object_or_404(
        ResourceSupplier,
        resource=resource,
        supplier__pk=supplier_pk
    )

    if request.method == 'POST':
        was_preferred = link.preferred
        supplier_name = link.supplier.supplier_name
        link.delete()

        # If we deleted the preferred supplier,
        # auto-promote the cheapest remaining one
        if was_preferred:
            next_best = ResourceSupplier.objects.filter(
                resource=resource,
                active=True
            ).order_by('supplier_rate').first()

            if next_best:
                next_best.preferred = True
                next_best.save()
                messages.success(
                    request,
                    f'"{supplier_name}" removed. '
                    f'"{next_best.supplier.supplier_name}" '
                    f'is now the preferred supplier.'
                )
            else:
                messages.success(
                    request,
                    f'"{supplier_name}" removed. '
                    f'Costing now uses resource master rate.'
                )
        else:
            messages.success(
                request,
                f'"{supplier_name}" removed from '
                f'"{resource.resource_name}".'
            )

    return redirect('resources:detail', pk=resource_pk)


@login_required
def resource_set_preferred(request, resource_pk, supplier_pk):
    """
    Sets one supplier as preferred for a resource.
    Clears preferred status from all other suppliers
    for this resource first.
    """
    from apps.resources.models import Resource

    resource = get_object_or_404(Resource, pk=resource_pk)

    if request.method == 'POST':
        with transaction.atomic():
            # Clear preferred from all links for this resource
            ResourceSupplier.objects.filter(
                resource=resource
            ).update(preferred=False)

            # Set the chosen one as preferred
            link = get_object_or_404(
                ResourceSupplier,
                resource=resource,
                supplier__pk=supplier_pk,
                active=True
            )
            link.preferred = True
            link.save()

            messages.success(
                request,
                f'"{link.supplier.supplier_name}" is now the '
                f'preferred supplier for "{resource.resource_name}". '
                f'Costing rate updated to '
                f'₹{link.supplier_rate}.'
            )

    return redirect('resources:detail', pk=resource_pk)


@login_required
def resource_update_supplier_rate(request, resource_pk, supplier_pk):
    """
    Updates the rate for a specific supplier-resource link.
    """
    from apps.resources.models import Resource

    resource = get_object_or_404(Resource, pk=resource_pk)
    link = get_object_or_404(
        ResourceSupplier,
        resource=resource,
        supplier__pk=supplier_pk
    )

    if request.method == 'POST':
        new_rate = request.POST.get('supplier_rate', '').strip()
        try:
            rate = float(new_rate)
            if rate < 0:
                raise ValueError()
            link.supplier_rate = rate
            link.save()
            messages.success(
                request,
                f'Rate for "{link.supplier.supplier_name}" '
                f'updated to ₹{rate}.'
            )
        except (TypeError, ValueError):
            messages.error(
                request,
                'Invalid rate. Please enter a positive number.'
            )

    return redirect('resources:detail', pk=resource_pk)

@login_required
def supplier_detail(request, pk):
    """
    Show a single supplier's profile page.

    Displays:
    - Supplier contact info (name, phone, GST)
    - Every resource this supplier is linked to, with their rate
    - Visual indicators for preferred status and active/inactive links
    - A summary: total resources supplied, preferred count, active count
    """

    # get_object_or_404: fetch Supplier with this PK from the DB.
    # If no Supplier has this PK, Django automatically returns a 404 page.
    # This is safer and shorter than:
    #   try:
    #       supplier = Supplier.objects.get(pk=pk)
    #   except Supplier.DoesNotExist:
    #       raise Http404
    supplier = get_object_or_404(Supplier, pk=pk)

    # Fetch all ResourceSupplier rows for this supplier.
    #
    # select_related('resource', 'resource__category') tells Django:
    #   "When you load each ResourceSupplier, also JOIN and load the
    #    related Resource row AND the Resource's category in the same
    #    SQL query."
    #
    # Without this, if a supplier has 20 resources, Django fires:
    #   1 query for ResourceSupplier rows
    #   20 queries for Resource rows (one per row) — the N+1 problem!
    # With select_related: just 1 query total. Always do this on FKs.
    #
    # We include ALL links (active and inactive) so staff can see
    # the complete history. The template will style them differently.
    resource_links = (
        ResourceSupplier.objects
        .filter(supplier=supplier)
    .select_related('resource')
        .order_by('resource__resource_name')  # alphabetical by resource name
    )

    # Build summary counts for the stats panel at the top of the page.
    # We use Python to count from the already-fetched queryset.
    # Calling .count() on a queryset fires a new SQL COUNT query.
    # Since resource_links isn't evaluated yet, these fire efficient queries.
    total_links = resource_links.count()
    active_links = resource_links.filter(active=True).count()
    preferred_links = resource_links.filter(preferred=True).count()

    # Calculate total spend potential: sum of (supplier_rate) for active links.
    # We import Decimal here to handle the case where there are no links
    # (sum of an empty sequence would be 0, but we want Decimal('0')).
    from decimal import Decimal
    total_value = sum(
        link.supplier_rate
        for link in resource_links.filter(active=True)
        # supplier_rate is a DecimalField, so arithmetic stays precise
    ) if active_links > 0 else Decimal('0')

    context = {
        'supplier': supplier,          # The Supplier object
        'resource_links': resource_links,  # QuerySet of ResourceSupplier rows
        'total_links': total_links,
        'active_links': active_links,
        'preferred_links': preferred_links,
        'total_value': total_value,
    }

    return render(request, 'suppliers/supplier_detail.html', context)