# apps/quotations/services.py
from decimal import Decimal
from datetime import date

from apps.core.models import SystemConfig
from apps.bom.models import BOMItem, WoodPart


def get_product_base_cost(product):
    """
    Mirrors the grand-total calculation in apps.costing.views.cost_sheet /
    costing_list exactly: Standard BOM (BOMItem.cost) + Dimensional BOM
    (WoodPart.cost). Kept here rather than importing from apps.costing
    since that view has no standalone calculation function to call —
    the logic is inline. If costing/views.py is ever refactored to expose
    a shared helper, switch this to call it instead of duplicating.
    """
    bom_total = sum(
        (item.cost for item in BOMItem.objects.filter(product=product).select_related('resource')),
        Decimal('0')
    )
    dimensional_total = sum(
        (part.cost for part in WoodPart.objects.filter(product=product).select_related('resource')),
        Decimal('0')
    )
    return bom_total + dimensional_total


def calculate_line_tax(base_cost, markup_percent, quantity, gst_rate, customer_state):
    """
    Returns the marked-up price, line subtotal, and CGST/SGST vs IGST
    breakdown for one quotation line, based on comparing the customer's
    state to the company's state (SystemConfig.company_state).
    """
    marked_up_price = base_cost + (base_cost * markup_percent / Decimal('100'))
    line_subtotal = marked_up_price * quantity

    company_state = SystemConfig.get_config().company_state
    same_state = customer_state.strip().lower() == company_state.strip().lower()

    tax_amount = line_subtotal * gst_rate / Decimal('100')

    if same_state:
        return {
            'marked_up_price': marked_up_price,
            'line_subtotal': line_subtotal,
            'tax_type': 'CGST_SGST',
            'cgst_amount': tax_amount / 2,
            'sgst_amount': tax_amount / 2,
            'igst_amount': Decimal('0'),
            'line_total': line_subtotal + tax_amount,
        }
    else:
        return {
            'marked_up_price': marked_up_price,
            'line_subtotal': line_subtotal,
            'tax_type': 'IGST',
            'cgst_amount': Decimal('0'),
            'sgst_amount': Decimal('0'),
            'igst_amount': tax_amount,
            'line_total': line_subtotal + tax_amount,
        }


def generate_quotation_number():
    """
    QTN-{year}-{sequence}, sequence resets each calendar year.
    Called inside transaction.atomic() in the view to avoid a race
    between the count and the save.
    """
    from .models import Quotation
    year = date.today().year
    prefix = f"QTN-{year}-"
    count = Quotation.objects.filter(quotation_number__startswith=prefix).count()
    return f"{prefix}{count + 1:04d}"