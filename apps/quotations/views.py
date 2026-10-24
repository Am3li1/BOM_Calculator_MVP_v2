# apps/quotations/views.py
from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, request
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator

from apps.core.decorators import admin_required, not_carpenter
from apps.core.constants import INDIA_STATES
from apps.products.models import Product
from apps.core.models import SystemConfig

from .models import Customer, MarkupTier, Quotation, QuotationItem, Invoice, InvoiceItem
from .forms import CustomerForm, QuotationItemFormSet
from .services import calculate_line_tax, get_product_base_cost, generate_quotation_number, generate_invoice_number


# ---------------------------------------------------------------------------
# Quotation list / detail — viewer access, matches Products/Resources pattern
# ---------------------------------------------------------------------------

@login_required
@not_carpenter
def quotation_list(request):
    quotations = Quotation.objects.select_related('customer').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        quotations = quotations.filter(
            Q(quotation_number__icontains=search) |
            Q(customer__name__icontains=search)
        )

    status = request.GET.get('status', '').strip()
    if status:
        quotations = quotations.filter(status=status)

    paginator = Paginator(quotations, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'quotations/list.html', {
        'page_title': 'Quotations',
        'page_obj': page_obj,
        'search': search,
        'status': status,
        'status_choices': Quotation.STATUS_CHOICES,
    })


@login_required
@not_carpenter
def quotation_detail(request, pk):
    quotation = get_object_or_404(
        Quotation.objects.select_related('customer').prefetch_related('items__product'),
        pk=pk
    )
    return render(request, 'quotations/detail.html', {
        'page_title': f'Quotation {quotation.quotation_number}',
        'quotation': quotation,
        'tax_summary': quotation.tax_summary,
        'company': SystemConfig.get_config(),
    })


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@login_required
@not_carpenter
def customer_list(request):
    customers = Customer.objects.filter(active=True).order_by('name')

    search = request.GET.get('search', '').strip()
    if search:
        customers = customers.filter(name__icontains=search)

    paginator = Paginator(customers, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'quotations/customer_list.html', {
        'page_title': 'Customers',
        'page_obj': page_obj,
        'search': search,
    })


@login_required
@not_carpenter
@admin_required
def customer_create(request):
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f'Customer "{customer.name}" added.')
            next_url = request.POST.get('next') or 'quotations:customer_list'
            return redirect(next_url)
    else:
        form = CustomerForm()

    return render(request, 'quotations/customer_form.html', {
        'page_title': 'Add Customer',
        'form': form,
        'india_states': INDIA_STATES,
    })


@login_required
@not_carpenter
def customer_search_json(request):
    """
    Read-only lookup for the type-to-filter customer combobox on the
    quotation_create form, mirroring the WoodPart resource combobox
    pattern (vanilla JS, no framework).
    """
    customers = Customer.objects.filter(active=True).values(
        'id', 'name', 'phone_number', 'state', 'gst_number'
    ).order_by('name')
    return JsonResponse(list(customers), safe=False)


@login_required
@not_carpenter
def product_cost_json(request, pk):
    """
    Returns the live cost-sheet total, HSN code, and GST rate for a
    product. Used by quotation_create's JS to show a live preview when a
    product row is picked — the authoritative values are recalculated
    and snapshotted server-side on save, this is display-only.
    """
    product = get_object_or_404(Product, pk=pk)
    base_cost = get_product_base_cost(product)
    return JsonResponse({
        'base_cost': str(base_cost),
        'hsn_code': product.hsn_code,
        'gst_rate': str(product.gst_rate),
    })


# ---------------------------------------------------------------------------
# Quotation create — admin only
# ---------------------------------------------------------------------------

@login_required
@not_carpenter
@admin_required
def quotation_create(request):
    if request.method == 'POST':
        customer_id = request.POST.get('customer')
        customer = get_object_or_404(Customer, pk=customer_id) if customer_id else None
        formset = QuotationItemFormSet(request.POST, instance=Quotation())

        if customer and formset.is_valid():
            with transaction.atomic():
                quotation = Quotation.objects.create(
                    quotation_number=generate_quotation_number(),
                    customer=customer,
                    created_by=request.user,
                    status='draft',
                    billing_address=request.POST.get('billing_address', '').strip(),
                    billing_state=request.POST.get('billing_state', '').strip(),
                    shipping_address=request.POST.get('shipping_address', '').strip(),
                    shipping_state=request.POST.get('shipping_state', '').strip(),
                )

                formset.instance = quotation
                items = formset.save(commit=False)

                total_taxable = Decimal('0')
                total_cgst = Decimal('0')
                total_sgst = Decimal('0')
                total_igst = Decimal('0')

                for item in items:
                    product = item.product
                    base_cost = get_product_base_cost(product)
                    markup_percent = item.markup_tier.percentage

                    result = calculate_line_tax(
                        base_cost=base_cost,
                        markup_percent=markup_percent,
                        quantity=item.quantity,
                        gst_rate=product.gst_rate,
                        customer_state=customer.state,
                    )

                    item.quotation = quotation
                    item.base_cost = base_cost
                    item.markup_percent = markup_percent
                    item.hsn_code = product.hsn_code
                    item.gst_rate = product.gst_rate
                    item.tax_type = result['tax_type']
                    item.cgst_amount = result['cgst_amount']
                    item.sgst_amount = result['sgst_amount']
                    item.igst_amount = result['igst_amount']
                    item.line_total = result['line_total']
                    item.save()

                    total_taxable += result['line_subtotal']
                    total_cgst += result['cgst_amount']
                    total_sgst += result['sgst_amount']
                    total_igst += result['igst_amount']

                # handle any deleted formset rows
                for obj in formset.deleted_objects:
                    obj.delete()

                quotation.total_taxable = total_taxable
                quotation.total_cgst = total_cgst
                quotation.total_sgst = total_sgst
                quotation.total_igst = total_igst
                quotation.grand_total = total_taxable + total_cgst + total_sgst + total_igst
                quotation.save()

            messages.success(request, f'Quotation {quotation.quotation_number} created.')
            return redirect('quotations:quotation_detail', pk=quotation.pk)
        else:
            if not customer:
                messages.error(request, 'Please select a customer.')
            if not formset.is_valid():
                messages.error(request, 'Please fix the errors in the product lines below.')
    else:
        formset = QuotationItemFormSet(instance=Quotation())

    return render(request, 'quotations/quotation_form.html', {
        'page_title': 'New Quotation',
        'formset': formset,
        'customers': Customer.objects.filter(active=True).order_by('name'),
        'products': Product.objects.filter(active=True, is_deleted=False).order_by('product_name'),
        'company_state': SystemConfig.get_config().company_state,
        'markup_tiers': list(MarkupTier.objects.filter(active=True).values('pk', 'percentage')),
        'india_states': INDIA_STATES,
    })


@login_required
@not_carpenter
@admin_required
def quotation_update_status(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)

    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in dict(Quotation.STATUS_CHOICES):
            if quotation.status == 'accepted' and new_status != 'accepted' and hasattr(quotation, 'invoice'):
                messages.error(
                    request,
                    "Can't change status — an invoice already exists for this quotation."
                )
                return redirect('quotations:quotation_detail', pk=pk)
            quotation.status = new_status
            quotation.save(update_fields=['status'])
            messages.success(request, f'Quotation marked as {quotation.get_status_display()}.')

    return redirect('quotations:quotation_detail', pk=pk)

# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

@login_required
@not_carpenter
def quotation_pdf(request, pk):
    from django.http import HttpResponse
    from .pdf import generate_quotation_pdf  # separate module — see next message

    quotation = get_object_or_404(
        Quotation.objects.select_related('customer').prefetch_related('items__product'),
        pk=pk
    )

    pdf_buffer = generate_quotation_pdf(quotation)
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{quotation.quotation_number}.pdf"'
    return response

@login_required
@not_carpenter
@admin_required
def quotation_edit(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)

    if quotation.status == 'accepted':
        messages.error(request, "Accepted quotations are locked and can't be edited.")
        return redirect('quotations:quotation_detail', pk=pk)

    if quotation.status != 'draft':
        messages.error(request, "Only draft quotations can be edited.")
        return redirect('quotations:quotation_detail', pk=pk)

    if request.method == 'POST':
        customer_id = request.POST.get('customer')
        customer = get_object_or_404(Customer, pk=customer_id) if customer_id else None
        formset = QuotationItemFormSet(request.POST, instance=quotation)

        if customer and formset.is_valid():
            with transaction.atomic():
                quotation.customer = customer
                quotation.billing_address = request.POST.get('billing_address', '').strip()
                quotation.billing_state = request.POST.get('billing_state', '').strip()
                quotation.shipping_address = request.POST.get('shipping_address', '').strip()
                quotation.shipping_state = request.POST.get('shipping_state', '').strip()
                items = formset.save(commit=False)

                total_taxable = Decimal('0')
                total_cgst = Decimal('0')
                total_sgst = Decimal('0')
                total_igst = Decimal('0')

                for item in items:
                    product = item.product
                    base_cost = get_product_base_cost(product)
                    markup_percent = item.markup_tier.percentage

                    result = calculate_line_tax(
                        base_cost=base_cost, markup_percent=markup_percent,
                        quantity=item.quantity, gst_rate=product.gst_rate,
                        customer_state=customer.state,
                    )

                    item.quotation = quotation
                    item.base_cost = base_cost
                    item.markup_percent = markup_percent
                    item.hsn_code = product.hsn_code
                    item.gst_rate = product.gst_rate
                    item.tax_type = result['tax_type']
                    item.cgst_amount = result['cgst_amount']
                    item.sgst_amount = result['sgst_amount']
                    item.igst_amount = result['igst_amount']
                    item.line_total = result['line_total']
                    item.save()

                    total_taxable += result['line_subtotal']
                    total_cgst += result['cgst_amount']
                    total_sgst += result['sgst_amount']
                    total_igst += result['igst_amount']

                for obj in formset.deleted_objects:
                    obj.delete()

                # Recompute totals from ALL remaining items, not just this
                # save's loop — safer against partial formset edits.
                remaining_items = quotation.items.all()
                quotation.total_taxable = sum((i.line_subtotal for i in remaining_items), Decimal('0'))
                quotation.total_cgst = sum((i.cgst_amount for i in remaining_items), Decimal('0'))
                quotation.total_sgst = sum((i.sgst_amount for i in remaining_items), Decimal('0'))
                quotation.total_igst = sum((i.igst_amount for i in remaining_items), Decimal('0'))
                quotation.grand_total = quotation.total_taxable + quotation.total_cgst + quotation.total_sgst + quotation.total_igst
                quotation.save()

            messages.success(request, f'Quotation {quotation.quotation_number} updated.')
            return redirect('quotations:quotation_detail', pk=quotation.pk)
        else:
            if not customer:
                messages.error(request, 'Please select a customer.')
            if not formset.is_valid():
                messages.error(request, 'Please fix the errors in the product lines below.')
    else:
        formset = QuotationItemFormSet(instance=quotation)

    return render(request, 'quotations/quotation_form.html', {
        'page_title': f'Edit {quotation.quotation_number}',
        'quotation': quotation,
        'formset': formset,
        'customers': Customer.objects.filter(active=True).order_by('name'),
        'products': Product.objects.filter(active=True, is_deleted=False).order_by('product_name'),
        'company_state': SystemConfig.get_config().company_state,
        'markup_tiers': list(MarkupTier.objects.filter(active=True).values('pk', 'percentage')),
        'india_states': INDIA_STATES,
    })


@login_required
@not_carpenter
@admin_required
def quotation_delete(request, pk):
    quotation = get_object_or_404(Quotation, pk=pk)

    if quotation.status == 'accepted':
        messages.error(request, "Accepted quotations are locked and can't be deleted.")
        return redirect('quotations:quotation_detail', pk=pk)
    
    if quotation.status != 'draft':
        messages.error(request, "Only draft quotations can be deleted.")
        return redirect('quotations:quotation_detail', pk=pk)

    if request.method == 'POST':
        number = quotation.quotation_number
        quotation.delete()
        messages.success(request, f'Quotation {number} deleted.')
        return redirect('quotations:quotation_list')

    return redirect('quotations:quotation_detail', pk=pk)

@login_required
@not_carpenter
@admin_required
def quotation_convert_to_invoice(request, pk):
    """
    Converts an accepted quotation into a draft invoice, copying its items
    as an independent snapshot (editing the invoice afterward never touches
    the quotation, and vice versa). Only runs once — a quotation can only
    ever produce one invoice (OneToOneField).
    """
    quotation = get_object_or_404(Quotation, pk=pk)

    if quotation.status != 'accepted':
        messages.error(request, "Only accepted quotations can be converted to an invoice.")
        return redirect('quotations:quotation_detail', pk=pk)

    if hasattr(quotation, 'invoice'):
        messages.error(request, f"An invoice already exists for this quotation: {quotation.invoice.invoice_number}.")
        return redirect('quotations:invoice_detail', pk=quotation.invoice.pk)

    if request.method == 'POST':
        with transaction.atomic():
            invoice = Invoice.objects.create(
                invoice_number=generate_invoice_number(),
                quotation=quotation,
                created_by=request.user,
                status='draft',
                billing_address=quotation.billing_address,
                billing_state=quotation.billing_state,
                shipping_address=quotation.shipping_address,
                shipping_state=quotation.shipping_state,
                total_taxable=quotation.total_taxable,
                total_cgst=quotation.total_cgst,
                total_sgst=quotation.total_sgst,
                total_igst=quotation.total_igst,
                grand_total=quotation.grand_total,
            )
            for item in quotation.items.all():
                InvoiceItem.objects.create(
                    invoice=invoice,
                    product=item.product,
                    base_cost=item.base_cost,
                    markup_tier=item.markup_tier,
                    markup_percent=item.markup_percent,
                    quantity=item.quantity,
                    hsn_code=item.hsn_code,
                    gst_rate=item.gst_rate,
                    tax_type=item.tax_type,
                    cgst_amount=item.cgst_amount,
                    sgst_amount=item.sgst_amount,
                    igst_amount=item.igst_amount,
                    line_total=item.line_total,
                )

        messages.success(request, f'Invoice {invoice.invoice_number} created as draft.')
        return redirect('quotations:invoice_detail', pk=invoice.pk)

    return redirect('quotations:quotation_detail', pk=pk)


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@login_required
@not_carpenter
def invoice_list(request):
    invoices = Invoice.objects.select_related('quotation__customer').order_by('-created_at')

    search = request.GET.get('search', '').strip()
    if search:
        invoices = invoices.filter(
            Q(invoice_number__icontains=search) |
            Q(quotation__customer__name__icontains=search)
        )

    status = request.GET.get('status', '').strip()
    if status:
        invoices = invoices.filter(status=status)

    paginator = Paginator(invoices, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'quotations/invoice_list.html', {
        'page_title': 'Invoices',
        'page_obj': page_obj,
        'search': search,
        'status': status,
        'status_choices': Invoice.STATUS_CHOICES,
    })


@login_required
@not_carpenter
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('quotation__customer').prefetch_related('items__product'),
        pk=pk
    )
    return render(request, 'quotations/invoice_detail.html', {
        'page_title': f'Invoice {invoice.invoice_number}',
        'invoice': invoice,
        'tax_summary': invoice.tax_summary,
        'company': SystemConfig.get_config(),
    })


@login_required
@not_carpenter
@admin_required
def invoice_edit(request, pk):
    """
    Drafts are a review window before finalizing, not a place to change
    line items — items are a fixed snapshot of the quotation at
    conversion time (per product decision). Only notes are editable here.
    """
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status != 'draft':
        messages.error(request, "Only draft invoices can be edited.")
        return redirect('quotations:invoice_detail', pk=pk)

    if request.method == 'POST':
        invoice.notes = request.POST.get('notes', '').strip()
        invoice.save(update_fields=['notes'])
        messages.success(request, f'Invoice {invoice.invoice_number} updated.')
        return redirect('quotations:invoice_detail', pk=invoice.pk)

    return render(request, 'quotations/invoice_form.html', {
        'page_title': f'Edit {invoice.invoice_number}',
        'invoice': invoice,
    })


@login_required
@not_carpenter
@admin_required
def invoice_finalize(request, pk):
    """
    One-way lock. No un-finalize path — GST invoice numbers must be
    gap-free and immutable once issued.
    """
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status != 'draft':
        messages.error(request, "Only draft invoices can be finalized.")
        return redirect('quotations:invoice_detail', pk=pk)

    if request.method == 'POST':
        from django.utils import timezone
        invoice.status = 'finalized'
        invoice.finalized_at = timezone.now()
        invoice.save(update_fields=['status', 'finalized_at'])
        messages.success(request, f'Invoice {invoice.invoice_number} finalized and locked.')

    return redirect('quotations:invoice_detail', pk=pk)


@login_required
@not_carpenter
@admin_required
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.status != 'draft':
        messages.error(request, "Only draft invoices can be deleted.")
        return redirect('quotations:invoice_detail', pk=pk)

    if request.method == 'POST':
        number = invoice.invoice_number
        invoice.delete()
        messages.success(request, f'Invoice {number} deleted.')
        return redirect('quotations:invoice_list')

    return redirect('quotations:invoice_detail', pk=pk)


@login_required
@not_carpenter
def invoice_pdf(request, pk):
    from django.http import HttpResponse
    from .pdf import generate_invoice_pdf

    invoice = get_object_or_404(
        Invoice.objects.select_related('quotation__customer').prefetch_related('items__product'),
        pk=pk
    )

    pdf_buffer = generate_invoice_pdf(invoice)
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{invoice.invoice_number}.pdf"'
    return response