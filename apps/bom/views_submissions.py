# apps/bom/views_submissions.py
#
# Admin side of carpenter submissions: create/share a magic link, review
# what came back, and approve (copy into the real BOM) or reject.
# The public form itself lives in apps/carpenter/views.py:link_form.

import ipaddress
import re
from datetime import timedelta
from urllib.parse import quote, urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.carpenter.models import BOMSubmission, SubmissionLine
from apps.core.decorators import admin_required, not_carpenter
from apps.products.models import Product
from apps.resources.models import DIMENSIONAL_UNIT_CHOICES

from .models import BOMItem, WoodPart
from .services import (
    LineError, apply_lines, clean_bom_line, clean_dimension_line, describe_result,
)

MAX_EXPIRY_DAYS = 30


def _link_url(request, submission):
    return request.build_absolute_uri(
        reverse('carpenter:link_form', kwargs={'token': submission.token})
    )


def _is_local_link(link):
    """True when the link points at localhost / an IP address. WhatsApp
    only turns real domain names into tappable links, and a phone can't
    reach the admin's own machine anyway."""
    host = urlsplit(link).hostname or ''
    if host == 'localhost' or host.endswith('.local'):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _whatsapp_url(submission, link):
    if submission.language == 'ta':
        greeting = f'வணக்கம் {submission.carpenter_name},' if submission.carpenter_name else 'வணக்கம்,'
        text = (f'{greeting} "{submission.product.product_name}" க்குத் தேவையான '
                f'பொருட்களை இந்த இணைப்பில் நிரப்பவும்:\n{link}')
    else:
        greeting = f'Hi {submission.carpenter_name},' if submission.carpenter_name else 'Hi,'
        text = (f'{greeting} please fill in the materials needed for '
                f'"{submission.product.product_name}" here:\n{link}')

    digits = re.sub(r'\D', '', submission.carpenter_phone or '')
    if len(digits) == 10:
        digits = '91' + digits      # bare Indian mobile number
    return f'https://wa.me/{digits}?text={quote(text)}'


@login_required
@not_carpenter
@admin_required
@require_POST
def submission_link_create(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk, is_deleted=False)

    try:
        days = int(request.POST.get('expiry_days') or BOMSubmission.DEFAULT_EXPIRY_DAYS)
    except ValueError:
        days = BOMSubmission.DEFAULT_EXPIRY_DAYS
    days = max(1, min(days, MAX_EXPIRY_DAYS))

    language = request.POST.get('language', 'en')
    if language not in dict(BOMSubmission.LANGUAGE_CHOICES):
        language = 'en'

    submission = BOMSubmission.objects.create(
        product=product,
        created_by=request.user,
        carpenter_name=request.POST.get('carpenter_name', '').strip()[:100],
        carpenter_phone=request.POST.get('carpenter_phone', '').strip()[:20],
        language=language,
        expires_at=timezone.now() + timedelta(days=days),
    )
    messages.success(request, 'Carpenter link created. Copy it or send it on WhatsApp below.')
    return redirect('bom:submission_detail', pk=submission.pk)


@login_required
@not_carpenter
@admin_required
def submission_list(request):
    submissions = (
        BOMSubmission.objects.select_related('product', 'created_by', 'reviewed_by')
        .annotate(
            status_rank=Case(
                When(status=BOMSubmission.STATUS_PENDING, then=Value(0)),
                When(status=BOMSubmission.STATUS_OPEN, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by('status_rank', '-submitted_at', '-created_at')
    )

    status = request.GET.get('status', '')
    if status in dict(BOMSubmission.STATUS_CHOICES):
        submissions = submissions.filter(status=status)

    product = None
    product_pk = request.GET.get('product', '')
    if product_pk.isdigit():
        product = Product.objects.filter(pk=product_pk).first()
        submissions = submissions.filter(product_id=product_pk)

    page = Paginator(submissions, 20).get_page(request.GET.get('page'))

    return render(request, 'bom/submission_list.html', {
        'page_title': 'Carpenter Submissions',
        'page_obj': page,
        'submissions': page.object_list,
        'status': status,
        'status_choices': BOMSubmission.STATUS_CHOICES,
        'product': product,
    })


def _render_detail(request, submission, posted=None, errors=None):
    product = submission.product
    lines = list(submission.lines.select_related('resource'))

    current_qty = dict(
        BOMItem.objects.filter(product=product).values_list('resource_id', 'quantity')
    )
    existing_dims = set(
        WoodPart.objects.filter(product=product).values_list('resource_id', 'part_name')
    )

    rows = []
    for line in lines:
        row = {'line': line}
        if line.line_type == SubmissionLine.TYPE_BOM:
            row['current_qty'] = current_qty.get(line.resource_id)
        else:
            row['already_in_bom'] = (line.resource_id, line.part_name) in existing_dims
        # Values to show in the editable inputs: what the admin last
        # posted (after a failed approve), else the carpenter's values.
        if posted is not None:
            row['include'] = posted.get(f'include_{line.pk}') == 'on'
            row['values'] = {
                f: posted.get(f'{f}_{line.pk}', '')
                for f in ('quantity', 'part', 'width', 'breadth', 'height', 'length', 'pieces',
                          'width_unit', 'breadth_unit', 'height_unit', 'length_unit')
            }
        else:
            row['include'] = True
            row['values'] = {
                'quantity': line.quantity, 'part': line.part_name,
                'width': line.width, 'breadth': line.breadth, 'height': line.height,
                'length': line.length, 'pieces': line.pieces,
                'width_unit': line.width_unit, 'breadth_unit': line.breadth_unit,
                'height_unit': line.height_unit, 'length_unit': line.length_unit,
            }
        rows.append(row)

    context = {
        'page_title': f'Carpenter Submission — {product.product_code}',
        'submission': submission,
        'editable': submission.status == BOMSubmission.STATUS_PENDING,
        'product': product,
        'bom_rows': [r for r in rows if r['line'].line_type == SubmissionLine.TYPE_BOM],
        'dim_rows': [r for r in rows if r['line'].line_type == SubmissionLine.TYPE_DIMENSION],
        'unit_choices': DIMENSIONAL_UNIT_CHOICES,
        'errors': errors or [],
    }
    if submission.status == BOMSubmission.STATUS_OPEN:
        link = _link_url(request, submission)
        context['link_url'] = link
        context['whatsapp_url'] = _whatsapp_url(submission, link)
        context['link_is_local'] = _is_local_link(link)
    return render(request, 'bom/submission_detail.html', context)


@login_required
@not_carpenter
@admin_required
def submission_detail(request, pk):
    submission = get_object_or_404(BOMSubmission.objects.select_related('product'), pk=pk)
    return _render_detail(request, submission)


@login_required
@not_carpenter
@admin_required
@require_POST
def submission_approve(request, pk):
    submission = get_object_or_404(BOMSubmission.objects.select_related('product'), pk=pk)
    if submission.status != BOMSubmission.STATUS_PENDING:
        messages.error(request, 'Only submissions waiting for review can be approved.')
        return redirect('bom:submission_detail', pk=pk)
    if submission.product.is_deleted:
        messages.error(request, 'This product has been deleted.')
        return redirect('bom:submission_detail', pk=pk)

    post = request.POST
    cleaned, errors = [], []
    for line in submission.lines.select_related('resource'):
        if post.get(f'include_{line.pk}') != 'on':
            continue
        label = (line.resource.resource_name if line.line_type == SubmissionLine.TYPE_BOM
                 else post.get(f'part_{line.pk}') or line.part_name)
        try:
            if line.line_type == SubmissionLine.TYPE_BOM:
                cleaned.append(clean_bom_line(line.resource_id, post.get(f'quantity_{line.pk}')))
            else:
                cleaned.append(clean_dimension_line(
                    line.resource_id,
                    post.get(f'part_{line.pk}'),
                    post.get(f'width_{line.pk}'),
                    post.get(f'breadth_{line.pk}'),
                    post.get(f'length_{line.pk}'),
                    post.get(f'pieces_{line.pk}'),
                    height=post.get(f'height_{line.pk}'),
                    width_unit=post.get(f'width_unit_{line.pk}'),
                    breadth_unit=post.get(f'breadth_unit_{line.pk}'),
                    height_unit=post.get(f'height_unit_{line.pk}'),
                    length_unit=post.get(f'length_unit_{line.pk}'),
                ))
        except LineError as e:
            errors.append(f'{label}: {e}')

    if not cleaned and not errors:
        errors.append('Tick at least one line to approve, or reject the submission instead.')
    if errors:
        return _render_detail(request, submission, posted=post, errors=errors)

    with transaction.atomic():
        locked = BOMSubmission.objects.select_for_update().get(pk=pk)
        if locked.status != BOMSubmission.STATUS_PENDING:
            messages.error(request, 'This submission was already reviewed.')
            return redirect('bom:submission_detail', pk=pk)
        result = apply_lines(submission.product, cleaned)
        locked.status = BOMSubmission.STATUS_APPROVED
        locked.reviewed_by = request.user
        locked.reviewed_at = timezone.now()
        locked.review_note = post.get('review_note', '').strip()
        locked.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])

    messages.success(request, f'Submission approved — {describe_result(*result)}.')
    return redirect('bom:list', product_pk=submission.product.pk)


@login_required
@not_carpenter
@admin_required
@require_POST
def submission_reject(request, pk):
    with transaction.atomic():
        submission = get_object_or_404(BOMSubmission.objects.select_for_update(), pk=pk)
        if submission.status != BOMSubmission.STATUS_PENDING:
            messages.error(request, 'Only submissions waiting for review can be rejected.')
            return redirect('bom:submission_detail', pk=pk)
        submission.status = BOMSubmission.STATUS_REJECTED
        submission.reviewed_by = request.user
        submission.reviewed_at = timezone.now()
        submission.review_note = request.POST.get('review_note', '').strip()
        submission.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])

    messages.success(request, 'Submission rejected. Nothing was added to the BOM.')
    return redirect('bom:submission_detail', pk=pk)


@login_required
@not_carpenter
@admin_required
@require_POST
def submission_revoke(request, pk):
    with transaction.atomic():
        submission = get_object_or_404(BOMSubmission.objects.select_for_update(), pk=pk)
        if submission.status != BOMSubmission.STATUS_OPEN:
            messages.error(request, 'Only unused links can be revoked.')
            return redirect('bom:submission_detail', pk=pk)
        submission.status = BOMSubmission.STATUS_REVOKED
        submission.save(update_fields=['status'])

    messages.success(request, 'Link revoked — it can no longer be used.')
    return redirect('bom:submission_detail', pk=pk)
