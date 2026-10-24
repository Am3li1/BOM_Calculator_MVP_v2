# apps/products/api.py
from decimal import Decimal

from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.http import require_GET
from django.utils import timezone

from .models import Product


def _get_product_cost(product):
    """
    Same calculation as apps.costing.views.cost_sheet's grand total:
    Standard BOM (BOMItem.cost) + Dimensional BOM (WoodPart.cost).
    Duplicated here rather than imported — matches the existing pattern
    in apps.quotations.services.get_product_base_cost (see that
    function's docstring: consolidate into a shared helper if
    apps.costing is ever refactored to expose one).
    """
    from apps.bom.models import BOMItem, WoodPart

    bom_total = sum(
        (item.cost for item in BOMItem.objects.filter(product=product).select_related('resource')),
        Decimal('0')
    )
    dimensional_total = sum(
        (part.cost for part in WoodPart.objects.filter(product=product).select_related('resource')),
        Decimal('0')
    )
    return bom_total + dimensional_total


@require_GET
def product_cost_api(request, product_code):
    """
    Read-only, cross-system endpoint. Elite Furniture Mart's separate
    sales system calls this to fetch a live manufacturing cost for the
    products it sources from Anna Furniture, keyed by product_code (the
    same stable identifier already used for import-matching — see
    CLAUDE.md's Upsert behaviour table).

    Auth is a shared-secret header, not Django sessions — this is a
    server-to-server call between two separate Django projects, not a
    logged-in browser request. Both systems sit on the same Tailscale
    network per CLAUDE.md's deployment notes, so this never touches the
    public internet, but the key still guards against anything else on
    the tailnet reading cost data.
    """
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != settings.EXTERNAL_API_KEY:
        return JsonResponse({'error': 'Invalid or missing API key'}, status=401)

    try:
        product = Product.objects.get(product_code__iexact=product_code, is_deleted=False)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)

    cost = _get_product_cost(product)

    return JsonResponse({
        'product_code': product.product_code,
        'product_name': product.product_name,
        'hsn_code': product.hsn_code,
        'gst_rate': str(product.gst_rate),
        'cost': str(cost),
        'active': product.active,
        'as_of': timezone.now().isoformat(),
    })