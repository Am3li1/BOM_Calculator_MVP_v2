# apps/products/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q

from .models import Product
from .forms import ProductForm


@login_required
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

    context = {
        'page_title': 'Products',
        'products': products,
        'search_query': search_query,
        'status_filter': status_filter,
        'total_count': products.count(),
    }
    return render(request, 'products/list.html', context)


@login_required
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