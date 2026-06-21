# apps/costing/views.py

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from collections import defaultdict
from django.db import models
from apps.products.models import Product
from apps.bom.models import BOMItem, WoodPart


@login_required
def costing_list(request):
    """
    Shows all active products with optional search filtering.
    """
    search_query = request.GET.get('search', '').strip()

    products = Product.objects.filter(
        is_deleted=False,
        active=True
    ).order_by('product_name')

    if search_query:
        products = products.filter(
            models.Q(product_name__icontains=search_query) |
            models.Q(product_code__icontains=search_query)
        )

    context = {
        'page_title': 'Cost Sheets',
        'products': products,
        'search_query': search_query,
    }
    return render(request, 'costing/list.html', context)


@login_required
def cost_sheet(request, product_pk):
    """
    Displays the full cost sheet for a single product.

    Cost logic:
    - Standard BOM is the sole source of product cost.
    - Dimensions section is informational only — shows measurements,
      not costs. Its materials are already costed in Standard BOM.
    - Grand total = Standard BOM total only.
    """
    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    bom_items = BOMItem.objects.filter(
        product=product
    ).select_related('resource').order_by(
        'resource__category', 'resource__resource_name'
    )

    wood_parts = WoodPart.objects.filter(
        product=product
    ).select_related('resource').order_by(
        'resource__category', 'part_name'
    )

    # ── Standard BOM: group by category ────────────────────────────
    bom_by_category = defaultdict(list)
    for item in bom_items:
        bom_by_category[item.resource.category].append(item)

    bom_category_totals = {}
    for category, items in bom_by_category.items():
        bom_category_totals[category] = sum(item.cost for item in items)

    # ── Grand total: Standard BOM only ─────────────────────────────
    # Dimensions are measurement records. Their material cost is already
    # captured in Standard BOM. Adding them again would double-count.
    grand_total = sum(bom_category_totals.values())

    # ── Category summary: BOM only ──────────────────────────────────
    category_summary = []
    for category, total in sorted(
        bom_category_totals.items(),
        key=lambda x: x[1],
        reverse=True
    ):
        percentage = (float(total) / float(grand_total) * 100) if grand_total > 0 else 0
        category_summary.append({
            'category':   category,
            'total':      total,
            'percentage': round(percentage, 1),
        })

    # ── Dimensions: grouped for display only ───────────────────────
    # No costs calculated here — purely for reference display.
    wood_by_category = defaultdict(list)
    for part in wood_parts:
        wood_by_category[part.resource.category].append(part)

    context = {
        'page_title': f'Cost Sheet — {product.product_code}',
        'product': product,

        # Standard BOM
        'bom_by_category':    dict(bom_by_category),
        'bom_category_totals': bom_category_totals,

        # Dimensions (display only, no costs)
        'wood_by_category':   dict(wood_by_category),

        # Totals
        'grand_total':        grand_total,

        # Category summary (BOM only)
        'category_summary':   category_summary,
    }
    return render(request, 'costing/cost_sheet.html', context)