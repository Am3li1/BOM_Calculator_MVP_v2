# apps/quotations/pdf.py
import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

from apps.core.models import SystemConfig


def generate_quotation_pdf(quotation):
    """
    Builds a one-page-ish A4 quotation PDF using ReportLab (pure Python,
    no system deps — keeps the Docker image lean per CLAUDE.md's stack
    notes). Pulls all figures from the already-snapshotted QuotationItem
    rows — never recalculates from live product/resource data, since a
    sent quotation must not change if rates move later.
    """
    config = SystemConfig.get_config()
    customer = quotation.customer

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm,
        leftMargin=16 * mm, rightMargin=16 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Title'], fontSize=16, spaceAfter=2)
    small = ParagraphStyle('Small', parent=styles['Normal'], fontSize=9, leading=12)
    small_right = ParagraphStyle('SmallRight', parent=small, alignment=TA_RIGHT)
    section_header = ParagraphStyle('SectionHeader', parent=styles['Heading3'], fontSize=11, spaceAfter=4)

    elements = []

    # ── Header: company + quotation meta ────────────────────────────
    header_table = Table([
        [
            Paragraph(f"<b>{config.company_name}</b>", title_style),
            Paragraph(
                f"<b>Quotation No:</b> {quotation.quotation_number}<br/>"
                f"<b>Date:</b> {quotation.created_at.strftime('%d %b %Y')}<br/>"
                f"<b>Status:</b> {quotation.get_status_display()}",
                small_right
            ),
        ]
    ], colWidths=[100 * mm, 74 * mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(header_table)

    if config.company_gstin:
        elements.append(Paragraph(f"GSTIN: {config.company_gstin}", small))
    elements.append(Paragraph(f"State: {config.company_state}", small))
    elements.append(Spacer(1, 10 * mm))

    # ── Bill To ──────────────────────────────────────────────────────
    elements.append(Paragraph("Bill To", section_header))
    customer_lines = [customer.name]
    if customer.address:
        customer_lines.append(customer.address)
    customer_lines.append(f"State: {customer.state}")
    if customer.gst_number:
        customer_lines.append(f"GSTIN: {customer.gst_number}")
    if customer.phone_number:
        customer_lines.append(f"Phone: {customer.phone_number}")
    elements.append(Paragraph("<br/>".join(customer_lines), small))
    elements.append(Spacer(1, 8 * mm))

    # ── Line items table ─────────────────────────────────────────────
    same_state_quotation = quotation.items.filter(tax_type='CGST_SGST').exists()
    tax_cols_header = ['CGST', 'SGST'] if same_state_quotation else ['IGST']

    header_row = ['#', 'Product', 'HSN', 'Qty', 'Rate (₹)'] + tax_cols_header + ['Line Total (₹)']
    rows = [header_row]

    for i, item in enumerate(quotation.items.select_related('product').all(), start=1):
        if item.tax_type == 'CGST_SGST':
            tax_cells = [
                f"{item.cgst_amount:,.2f}\n({item.gst_rate / 2:.1f}%)",
                f"{item.sgst_amount:,.2f}\n({item.gst_rate / 2:.1f}%)",
            ]
        else:
            tax_cells = [f"{item.igst_amount:,.2f}\n({item.gst_rate:.1f}%)"]

        rows.append([
            str(i),
            item.product.product_name,
            item.hsn_code or '—',
            str(item.quantity),
            f"{item.marked_up_price:,.2f}",
            *tax_cells,
            f"{item.line_total:,.2f}",
        ])

    col_widths = [8 * mm, 52 * mm, 18 * mm, 12 * mm, 22 * mm] + \
                 ([20 * mm, 20 * mm] if same_state_quotation else [22 * mm]) + [24 * mm]

    items_table = Table(rows, colWidths=col_widths, repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a1f3a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (2, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f7f7f9')]),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 8 * mm))

    # ── Tax summary (grouped by rate, from Quotation.tax_summary) ────
    elements.append(Paragraph("Tax Summary", section_header))
    summary_rows = [['Taxable @ Rate', 'Taxable Amount (₹)'] + tax_cols_header]
    for bucket in quotation.tax_summary:
        if same_state_quotation:
            summary_rows.append([
                f"{bucket['rate']:.1f}%",
                f"{bucket['taxable']:,.2f}",
                f"{bucket['cgst']:,.2f}",
                f"{bucket['sgst']:,.2f}",
            ])
        else:
            summary_rows.append([
                f"{bucket['rate']:.1f}%",
                f"{bucket['taxable']:,.2f}",
                f"{bucket['igst']:,.2f}",
            ])

    summary_table = Table(summary_rows, colWidths=[40 * mm] + [35 * mm] * len(tax_cols_header) * 0 + ([35*mm]*(2 if same_state_quotation else 1)) + [35*mm] if False else None)
    # (colWidths simplified below to avoid the conditional mess above)
    summary_table = Table(summary_rows, colWidths=None)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeee')),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 6 * mm))

    # ── Grand total block ──────────────────────────────────────────
    totals_rows = [
        ['Taxable Total', f"₹ {quotation.total_taxable:,.2f}"],
    ]
    if same_state_quotation:
        totals_rows.append(['CGST', f"₹ {quotation.total_cgst:,.2f}"])
        totals_rows.append(['SGST', f"₹ {quotation.total_sgst:,.2f}"])
    if quotation.total_igst:
        totals_rows.append(['IGST', f"₹ {quotation.total_igst:,.2f}"])
    totals_rows.append(['Grand Total', f"₹ {quotation.grand_total:,.2f}"])

    totals_table = Table(totals_rows, colWidths=[130 * mm, 44 * mm])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 11),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.black),
        ('TOPPADDING', (0, -1), (-1, -1), 6),
    ]))
    elements.append(totals_table)

    if quotation.notes:
        elements.append(Spacer(1, 8 * mm))
        elements.append(Paragraph("Notes", section_header))
        elements.append(Paragraph(quotation.notes, small))

    doc.build(elements)
    buffer.seek(0)
    return buffer