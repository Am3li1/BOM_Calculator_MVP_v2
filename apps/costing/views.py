# apps/costing/views.py

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from collections import defaultdict

from apps.products.models import Product
from apps.bom.models import BOMItem, WoodPart


@login_required
def costing_list(request):
    """
    Shows all active products so the user can pick one
    to view its cost sheet.
    """
    products = Product.objects.filter(
        is_deleted=False,
        active=True
    ).order_by('product_name')

    context = {
        'page_title': 'Cost Sheets',
        'products': products,
    }
    return render(request, 'costing/list.html', context)


@login_required
def cost_sheet(request, product_pk):
    """
    Displays the full cost sheet for a single product.

    This view does all the calculation work so the template
    stays clean and only handles display.
    """
    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    # ── Fetch all BOM items and Wood Parts ──────────────────────────
    bom_items  = BOMItem.objects.filter(
        product=product
    ).select_related('resource').order_by('resource__category', 'resource__resource_name')

    wood_parts = WoodPart.objects.filter(
        product=product
    ).select_related('resource').order_by('resource__category', 'part_name')

    # ── Build category groups for standard BOM ──────────────────────
    # We want to display BOM items grouped by category:
    #   Wood:     item1, item2  → subtotal
    #   Labour:   item3         → subtotal
    #   Hardware: item4, item5  → subtotal
    #
    # defaultdict(list) creates a dict that automatically starts
    # each new key with an empty list — no KeyError possible.

    bom_by_category = defaultdict(list)
    for item in bom_items:
        bom_by_category[item.resource.category].append(item)

    # Calculate subtotal per category
    bom_category_totals = {}
    for category, items in bom_by_category.items():
        bom_category_totals[category] = sum(item.cost for item in items)

    # ── Build category groups for Wood Parts ────────────────────────
    wood_by_category = defaultdict(list)
    for part in wood_parts:
        wood_by_category[part.resource.category].append(part)

    wood_category_totals = {}
    for category, parts in wood_by_category.items():
        wood_category_totals[category] = sum(part.cost for part in parts)

    # ── Grand totals ────────────────────────────────────────────────
    total_bom_cost  = sum(bom_category_totals.values())
    total_wood_cost = sum(wood_category_totals.values())
    grand_total     = float(total_bom_cost) + float(total_wood_cost)

    # ── Summary: all categories combined ───────────────────────────
    # Merge both dicts into one summary for the category table
    all_category_totals = defaultdict(float)
    for category, total in bom_category_totals.items():
        all_category_totals[category] += float(total)
    for category, total in wood_category_totals.items():
        all_category_totals[category] += float(total)

    # Sort summary by total descending, and pre-calculate percentage
    # We do this in the view — never in the template — to avoid
    # rounding errors from Django's {% widthratio %} tag.
    category_summary = []
    for category, total in sorted(
        all_category_totals.items(),
        key=lambda x: x[1],
        reverse=True
    ):
        percentage = (total / grand_total * 100) if grand_total > 0 else 0
        category_summary.append({
            'category': category,
            'total': total,
            'percentage': round(percentage, 1),
        })

    context = {
        'page_title': f'Cost Sheet — {product.product_code}',
        'product': product,

        # Grouped BOM data
        'bom_by_category': dict(bom_by_category),
        'bom_category_totals': bom_category_totals,

        # Grouped Wood data
        'wood_by_category': dict(wood_by_category),
        'wood_category_totals': wood_category_totals,

        # Totals
        'total_bom_cost': total_bom_cost,
        'total_wood_cost': total_wood_cost,
        'grand_total': grand_total,

        # Summary table
        'category_summary': category_summary,
    }
    return render(request, 'costing/cost_sheet.html', context)