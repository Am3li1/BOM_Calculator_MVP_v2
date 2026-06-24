# apps/products/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from apps.core.decorators import admin_required
from django.contrib import messages
from django.db.models import Q

from .models import Product
from .forms import ProductForm


@login_required
@admin_required
def product_list(request):
    """Shows all non-deleted products with search."""

    products = Product.objects.filter(is_deleted=False)

    # ── Search ──────────────────────────────────────────────────────
    search_query = request.GET.get('search', '').strip()
    if search_query:
        products = products.filter(
            Q(product_name__icontains=search_query) |
            Q(product_code__icontains=search_query)
        )

    # ── Status Filter ────────────────────────────────────────────────
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        products = products.filter(active=True)
    elif status_filter == 'inactive':
        products = products.filter(active=False)

    paginator = Paginator(products, 25)
    page_obj  = paginator.get_page(request.GET.get('page'))

    context = {
        'page_title': 'Products',
        'products': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_count': products.count(),
    }
    return render(request, 'products/list.html', context)


@login_required
@admin_required
def product_create(request):
    """
    Create a new product.
    
    Special case: if a soft-deleted product with the same code exists,
    restore it and update its details instead of creating a duplicate row.
    This keeps the database clean and preserves historical BOM data.
    """
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid():
            product_code = form.cleaned_data['product_code']

            # ── Check for a soft-deleted product with the same code ──
            existing = Product.objects.filter(
                product_code__iexact=product_code,
                is_deleted=True
            ).first()

            if existing:
                # Restore it: update fields and un-delete
                existing.product_name = form.cleaned_data['product_name']
                existing.active = form.cleaned_data['active']
                existing.is_deleted = False
                existing.save()
                messages.success(
                    request,
                    f'Product "{existing.product_name}" has been restored '
                    f'and updated successfully.'
                )
            else:
                # Normal creation
                product = form.save()
                messages.success(
                    request,
                    f'Product "{product.product_name}" created successfully.'
                )

            return redirect('products:list')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = ProductForm()

    return render(request, 'products/form.html', {
        'page_title': 'Add Product',
        'form': form,
        'form_title': 'Add New Product',
        'submit_label': 'Create Product',
    })


@login_required
@admin_required
def product_edit(request, pk):
    """Edit an existing product."""
    product = get_object_or_404(Product, pk=pk, is_deleted=False)

    if request.method == 'POST':
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'Product "{product.product_name}" updated successfully.'
            )
            return redirect('products:list')
        else:
            messages.error(request, 'Please fix the errors below.')
    else:
        form = ProductForm(instance=product)

    return render(request, 'products/form.html', {
        'page_title': f'Edit — {product.product_name}',
        'form': form,
        'form_title': f'Edit Product: {product.product_code}',
        'submit_label': 'Save Changes',
        'product': product,
    })


@login_required
@admin_required
def product_delete(request, pk):
    """
    Soft delete — marks product as deleted but keeps data.
    Only responds to POST for security (no accidental GETs).
    """
    product = get_object_or_404(Product, pk=pk, is_deleted=False)

    if request.method == 'POST':
        product_name = product.product_name
        product.delete()   # calls our custom soft-delete method
        messages.success(
            request,
            f'Product "{product_name}" has been removed.'
        )

    return redirect('products:list')

@login_required
@admin_required
def clone_product(request, pk):
    """
    Clones an existing product including all its BOM items and Wood Parts.

    GET:  Shows a confirmation form asking for the new product name.
    POST: Performs the clone and redirects to the new product's BOM page.

    The original product is never modified.
    Each cloned BOMItem and WoodPart becomes a completely independent
    database record — changes to the clone do not affect the original.
    """
    from django.db import transaction
    from apps.bom.models import BOMItem, WoodPart
    import re

    original = get_object_or_404(Product, pk=pk, is_deleted=False)

    # Pre-fill the suggested name so the user has something to edit
    suggested_name = f'Copy of {original.product_name}'

    if request.method == 'POST':
        new_name = request.POST.get('new_product_name', '').strip()
        new_code = request.POST.get('new_product_code', '').strip()

        # Validation
        errors = []
        if not new_name:
            errors.append('Product name is required.')
        if not new_code:
            errors.append('Product code is required.')
        if new_code and Product.objects.filter(
            product_code=new_code, is_deleted=False
        ).exists():
            errors.append(
                f'Product code "{new_code}" already exists. '
                f'Please choose a different code.'
            )

        if errors:
            for error in errors:
                messages.error(request, error)
            context = {
                'page_title': f'Clone — {original.product_name}',
                'original': original,
                'suggested_name': new_name or suggested_name,
                'suggested_code': new_code,
            }
            return render(request, 'products/clone.html', context)

        # ── Perform the clone inside a transaction ──────────────────
        # If anything fails, the entire operation rolls back.
        # We never end up with a half-cloned product.

        try:
            with transaction.atomic():

                # Step 1: Create the new Product record
                # We read the original's field values, then save
                # as a brand new object by not specifying pk.
                cloned_product = Product(
                    product_name = new_name,
                    product_code = new_code,
                    active       = original.active,
                    is_deleted   = False,
                )
                cloned_product.save()

                # Step 2: Copy all BOM Items
                # For each BOMItem on the original, create a new
                # BOMItem pointing to the cloned product.
                # The resource stays the same — we share the reference.
                original_bom_items = BOMItem.objects.filter(
                    product=original
                ).select_related('resource')

                bom_count = 0
                for item in original_bom_items:
                    BOMItem.objects.create(
                        product  = cloned_product,  # ← new product
                        resource = item.resource,   # ← same resource
                        quantity = item.quantity,   # ← copied value
                    )
                    bom_count += 1

                # Step 3: Copy all Wood Parts
                original_wood_parts = WoodPart.objects.filter(
                    product=original
                ).select_related('resource')

                wood_count = 0
                for part in original_wood_parts:
                    WoodPart.objects.create(
                        product      = cloned_product,
                        resource     = part.resource,
                        part_name    = part.part_name,
                        width        = part.width,
                        breadth      = part.breadth,
                        length       = part.length,
                        pieces       = part.pieces,
                        formula_type = part.formula_type,
                    )
                    wood_count += 1

            # Clone successful
            messages.success(
                request,
                f'"{original.product_name}" cloned successfully as '
                f'"{new_name}". '
                f'Copied {bom_count} BOM item(s) and {wood_count} wood part(s). '
                f'You can now edit the cloned product.'
            )

            # Redirect to the cloned product's BOM page
            # so the user can immediately start making changes
            return redirect('bom:list', product_pk=cloned_product.pk)

        except Exception as e:
            messages.error(
                request,
                f'Clone failed due to an unexpected error: {e}'
            )

    # Generate a suggested product code from the new name
    suggested_code = f'COPY-{original.product_code}'[:30]

    context = {
        'page_title': f'Clone — {original.product_name}',
        'original': original,
        'suggested_name': suggested_name,
        'suggested_code': suggested_code,
    }
    return render(request, 'products/clone.html', context)