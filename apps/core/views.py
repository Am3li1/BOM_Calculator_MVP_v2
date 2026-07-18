# apps/core/views.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.products.models import Product
from apps.resources.models import Resource
from apps.bom.models import BOMItem, WoodPart
from apps.suppliers.models import Supplier


@login_required
def dashboard(request):
    """
    Main dashboard view.
    
    @login_required means: if the user is not logged in,
    Django automatically redirects them to LOGIN_URL
    (which we set in settings.py as /accounts/login/)
    """

    # ── Summary Counts ──────────────────────────────────────────────
    total_products = Product.objects.filter(is_deleted=False).count()
    total_resources = Resource.objects.filter(active=True).count()
    total_bom_items = BOMItem.objects.count()
    total_wood_parts = WoodPart.objects.count()
    total_suppliers  = Supplier.objects.filter(active=True).count()

    # Portfolio cost = Standard BOM + Dimensional BOM, across all
    # products (rule change — see CLAUDE.md for history).
    # Uses effective_rate (supplier/override aware) via Python property.
    all_bom_items    = BOMItem.objects.select_related('resource').all()
    all_wood_parts   = WoodPart.objects.select_related('resource').all()
    portfolio_cost   = (
        sum(item.cost for item in all_bom_items)
        + sum(part.cost for part in all_wood_parts)
    )

    # ── Recently Updated Resources ──────────────────────────────────
    recent_resources = Resource.objects.filter(
        active=True
    ).order_by('-updated_at')[:5]

    # ── Recently Added Products ─────────────────────────────────────
    recent_products = Product.objects.filter(
        is_deleted=False
    ).order_by('-created_at')[:5]

    context = {
        'total_products': total_products,
        'total_resources': total_resources,
        'total_bom_items': total_bom_items,
        'total_wood_parts': total_wood_parts,
        'total_suppliers': total_suppliers,
        'portfolio_cost': portfolio_cost,
        'recent_resources': recent_resources,
        'recent_products': recent_products,
        'page_title': 'Dashboard',
    }

    return render(request, 'core/dashboard.html', context)