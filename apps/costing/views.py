# apps/costing/views.py

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from collections import defaultdict
from django.db import models
from apps.products.models import Product
from apps.bom.models import BOMItem, WoodPart
import io
from decimal import Decimal
from datetime import date
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from django.http import HttpResponse


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


@login_required
def export_full_workbook(request):
    """
    Exports the entire database as a single Excel workbook with 7 sheets:
        1. Products
        2. Resources
        3. Suppliers
        4. SupplierRates
        5. BOM
        6. Dimensions
        7. CostSummary

    All data comes from the live database — not from any previously
    uploaded files. Nothing is saved to disk; the workbook is built
    in memory and sent directly to the browser as a download.
    """
    from apps.products.models import Product
    from apps.resources.models import Resource
    from apps.suppliers.models import Supplier, ResourceSupplier
    from apps.bom.models import BOMItem, WoodPart

    # ── Fetch all data up front ───────────────────────────────────────
    # select_related() tells Django to JOIN the related table in one
    # SQL query instead of hitting the database once per row.
    products = Product.objects.filter(
        is_deleted=False
    ).order_by('product_name')

    resources = Resource.objects.all().order_by('category', 'resource_name')

    suppliers = Supplier.objects.all().order_by('supplier_name')

    supplier_rates = ResourceSupplier.objects.select_related(
        'supplier', 'resource'
    ).order_by('resource__category', 'resource__resource_name')

    bom_items = BOMItem.objects.select_related(
        'product', 'resource'
    ).filter(
        product__is_deleted=False
    ).order_by('product__product_name', 'resource__category', 'resource__resource_name')

    wood_parts = WoodPart.objects.select_related(
        'product', 'resource'
    ).filter(
        product__is_deleted=False
    ).order_by('product__product_name', 'part_name')

    # ── Create workbook ───────────────────────────────────────────────
    wb = openpyxl.Workbook()

    # ── Shared style helpers ──────────────────────────────────────────
    # Define once, reuse across all 7 sheets.

    def make_header_style():
        return {
            'fill': PatternFill("solid", fgColor="1a1f3a"),
            'font': Font(color="FFFFFF", bold=True, size=10),
            'align': Alignment(horizontal="center", vertical="center"),
        }

    def write_headers(ws, headers):
        """Writes a styled header row to a sheet."""
        ws.append(headers)
        s = make_header_style()
        for cell in ws[ws.max_row]:
            cell.fill = s['fill']
            cell.font = s['font']
            cell.alignment = s['align']
        ws.row_dimensions[ws.max_row].height = 20

    def set_col_widths(ws, widths):
        """Sets column widths. widths is a list of integers, one per column."""
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width

    def stripe_row(ws, row_num):
        """Light grey fill for even rows — makes large tables easier to read."""
        if row_num % 2 == 0:
            grey = PatternFill("solid", fgColor="F7F7F7")
            for cell in ws[row_num]:
                cell.fill = grey

    thin = Side(style='thin', color="DDDDDD")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def apply_border(ws):
        """Applies a thin border to every cell that has content."""
        for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
            for cell in row:
                cell.border = border

    # ════════════════════════════════════════════════════════════════
    # SHEET 1 — Products
    # ════════════════════════════════════════════════════════════════
    ws_products = wb.active
    ws_products.title = "Products"

    write_headers(ws_products, [
        "Product Code", "Product Name", "Active", "Created At"
    ])

    for i, p in enumerate(products, start=2):
        ws_products.append([
            p.product_code,
            p.product_name,
            "Yes" if p.active else "No",
            p.created_at.strftime('%d %b %Y') if p.created_at else '',
        ])
        stripe_row(ws_products, i)

    set_col_widths(ws_products, [18, 40, 8, 16])
    apply_border(ws_products)
    ws_products.freeze_panes = "A2"

    # ════════════════════════════════════════════════════════════════
    # SHEET 2 — Resources
    # ════════════════════════════════════════════════════════════════
    ws_resources = wb.create_sheet("Resources")

    write_headers(ws_resources, [
        "Resource Name", "Category", "Unit",
        "Master Rate (₹)", "Effective Rate (₹)", "Rate Source",
        "Override Rate (₹)", "Override Reason", "Active"
    ])

    for i, r in enumerate(resources, start=2):
        rate_source = r.effective_rate_source
        ws_resources.append([
            r.resource_name,
            r.category,
            r.unit,
            float(r.rate),
            float(r.effective_rate),
            rate_source['label'],
            float(r.manual_override_rate) if r.manual_override_rate else '',
            r.override_reason or '',
            "Yes" if r.active else "No",
        ])
        # Format the rate columns as currency
        row = ws_resources[ws_resources.max_row]
        row[3].number_format = '₹#,##0.00'
        row[4].number_format = '₹#,##0.00'
        if r.manual_override_rate:
            row[6].number_format = '₹#,##0.00'
        stripe_row(ws_resources, i)

    set_col_widths(ws_resources, [28, 18, 10, 16, 16, 18, 16, 24, 8])
    apply_border(ws_resources)
    ws_resources.freeze_panes = "A2"

    # ════════════════════════════════════════════════════════════════
    # SHEET 3 — Suppliers
    # ════════════════════════════════════════════════════════════════
    ws_suppliers = wb.create_sheet("Suppliers")

    write_headers(ws_suppliers, [
        "Supplier Name", "Phone Number", "GST Number",
        "Active", "Resources Linked"
    ])

    for i, s in enumerate(suppliers, start=2):
        ws_suppliers.append([
            s.supplier_name,
            s.phone_number or '',
            s.gst_number or '',
            "Yes" if s.active else "No",
            s.resource_count,
        ])
        stripe_row(ws_suppliers, i)

    set_col_widths(ws_suppliers, [32, 16, 18, 8, 16])
    apply_border(ws_suppliers)
    ws_suppliers.freeze_panes = "A2"

    # ════════════════════════════════════════════════════════════════
    # SHEET 4 — Supplier Rates
    # ════════════════════════════════════════════════════════════════
    ws_rates = wb.create_sheet("SupplierRates")

    write_headers(ws_rates, [
        "Supplier Name", "Resource Name", "Category", "Unit",
        "Supplier Rate (₹)", "Preferred", "Active"
    ])

    for i, link in enumerate(supplier_rates, start=2):
        ws_rates.append([
            link.supplier.supplier_name,
            link.resource.resource_name,
            link.resource.category,
            link.resource.unit,
            float(link.supplier_rate),
            "Yes" if link.preferred else "No",
            "Yes" if link.active else "No",
        ])
        row = ws_rates[ws_rates.max_row]
        row[4].number_format = '₹#,##0.00'

        # Highlight preferred supplier rows in soft green
        if link.preferred:
            green = PatternFill("solid", fgColor="E8F5E9")
            for cell in ws_rates[ws_rates.max_row]:
                cell.fill = green
        else:
            stripe_row(ws_rates, i)

    set_col_widths(ws_rates, [28, 28, 18, 10, 18, 10, 8])
    apply_border(ws_rates)
    ws_rates.freeze_panes = "A2"

    # ════════════════════════════════════════════════════════════════
    # SHEET 5 — BOM
    # ════════════════════════════════════════════════════════════════
    ws_bom = wb.create_sheet("BOM")

    write_headers(ws_bom, [
        "Product Code", "Product Name", "Resource Name",
        "Category", "Unit", "Quantity", "Rate (₹)", "Cost (₹)"
    ])

    for i, item in enumerate(bom_items, start=2):
        ws_bom.append([
            item.product.product_code,
            item.product.product_name,
            item.resource.resource_name,
            item.resource.category,
            item.resource.unit,
            float(item.quantity),
            float(item.resource.effective_rate),
            float(item.cost),
        ])
        row = ws_bom[ws_bom.max_row]
        row[5].number_format = '#,##0.0000'
        row[6].number_format = '₹#,##0.00'
        row[7].number_format = '₹#,##0.00'
        stripe_row(ws_bom, i)

    set_col_widths(ws_bom, [16, 32, 28, 18, 10, 12, 14, 14])
    apply_border(ws_bom)
    ws_bom.freeze_panes = "A2"

    # ════════════════════════════════════════════════════════════════
    # SHEET 6 — Dimensions (WoodParts)
    # ════════════════════════════════════════════════════════════════
    ws_dims = wb.create_sheet("Dimensions")

    write_headers(ws_dims, [
        "Product Code", "Product Name", "Part Name", "Resource",
        "Width", "Breadth", "Length", "Pieces", "Formula", "Calc. Qty"
    ])

    for i, part in enumerate(wood_parts, start=2):
        ws_dims.append([
            part.product.product_code,
            part.product.product_name,
            part.part_name,
            part.resource.resource_name,
            float(part.width),
            float(part.breadth),
            float(part.length),
            part.pieces,
            part.get_formula_type_display(),
            float(part.calculated_quantity),
        ])
        row = ws_dims[ws_dims.max_row]
        row[9].number_format = '#,##0.0000'
        stripe_row(ws_dims, i)

    set_col_widths(ws_dims, [16, 32, 24, 24, 10, 10, 10, 8, 14, 12])
    apply_border(ws_dims)
    ws_dims.freeze_panes = "A2"

    # ════════════════════════════════════════════════════════════════
    # SHEET 7 — Cost Summary (one row per product)
    # ════════════════════════════════════════════════════════════════
    ws_summary = wb.create_sheet("CostSummary")

    write_headers(ws_summary, [
        "Product Code", "Product Name", "BOM Items",
        "Total Cost (₹)", "Active"
    ])

    # Group BOM items by product to calculate per-product totals.
    # We use a dict keyed by product pk.
    from collections import defaultdict
    product_costs = defaultdict(lambda: {'items': 0, 'total': Decimal('0')})

    for item in bom_items:
        pk = item.product.pk
        product_costs[pk]['product'] = item.product
        product_costs[pk]['items'] += 1
        product_costs[pk]['total'] += item.cost

    # Also include products that have no BOM items yet
    # so every product appears in the summary.
    all_products_map = {p.pk: p for p in products}

    summary_rows = []
    for pk, p in all_products_map.items():
        data = product_costs.get(pk, {})
        summary_rows.append({
            'product': p,
            'items':   data.get('items', 0),
            'total':   data.get('total', Decimal('0')),
        })

    # Sort by total cost descending so most expensive products are at the top
    summary_rows.sort(key=lambda x: x['total'], reverse=True)

    for i, row_data in enumerate(summary_rows, start=2):
        ws_summary.append([
            row_data['product'].product_code,
            row_data['product'].product_name,
            row_data['items'],
            float(row_data['total']),
            "Yes" if row_data['product'].active else "No",
        ])
        row = ws_summary[ws_summary.max_row]
        row[3].number_format = '₹#,##0.00'
        stripe_row(ws_summary, i)

    # Grand total row at the bottom of cost summary
    grand_total_all = sum(r['total'] for r in summary_rows)
    ws_summary.append([])
    ws_summary.append([
        "TOTAL", "",
        sum(r['items'] for r in summary_rows),
        float(grand_total_all),
        "",
    ])
    gt_row = ws_summary[ws_summary.max_row]
    grand_fill = PatternFill("solid", fgColor="1a1f3a")
    grand_font = Font(color="FFFFFF", bold=True)
    for cell in gt_row:
        cell.fill = grand_fill
        cell.font = grand_font
    gt_row[3].number_format = '₹#,##0.00'

    set_col_widths(ws_summary, [18, 38, 12, 18, 8])
    apply_border(ws_summary)
    ws_summary.freeze_panes = "A2"

    # ── Save to buffer and return as download ─────────────────────────
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"Product_Costing_Export_{date.today().strftime('%Y%m%d')}.xlsx"

    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response