# apps/imports/views.py

import os
import shutil
import tempfile

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import ImportLog
from .services import validate_workbook, import_workbook


@login_required
def upload(request):
    recent_logs = ImportLog.objects.order_by('-created_at')[:10]

    sheets_info = [
        ('Resource',      'Materials, rates, categories'),
        ('Products',      'Product names'),
        ('BOM',           'Bill of materials per product'),
        ('Wood, Ply MDF', 'Dimension entries per product'),
        ('Suppliers',     'Supplier names and phone numbers'),
    ]

    if request.method == 'POST':
        uploaded_file = request.FILES.get('workbook')

        if not uploaded_file:
            messages.error(request, 'Please select a file.')
            return redirect('imports:upload')

        if not uploaded_file.name.endswith(('.xlsx', '.xls')):
            messages.error(request,
                f'"{uploaded_file.name}" is not a valid Excel file.')
            return redirect('imports:upload')

        max_size = 10 * 1024 * 1024
        if uploaded_file.size > max_size:
            messages.error(request,
                f'File too large. Maximum is 10MB.')
            return redirect('imports:upload')

        # ── Create log record immediately ────────────────────────
        # This records EVERY attempt including validation failures
        log = ImportLog.objects.create(
            file_name=uploaded_file.name,
            uploaded_by=request.user,
            status='pending',
            import_type='full',
        )

        # Save to temp file
        suffix = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(uploaded_file, tmp)
            tmp_path = tmp.name

        try:
            # ── Phase 1: Validate ────────────────────────────────
            validation = validate_workbook(tmp_path)

            if not validation['valid']:
                # Record the validation failure in the log
                error_lines = [
                    f"[{e['sheet']}] Row {e['row']}: {e['message']}"
                    for e in validation['errors']
                ]
                log.status                 = 'validation_failed'
                log.validation_error_count = validation['error_count']
                log.error_log              = '\n'.join(error_lines)
                log.save()

                os.unlink(tmp_path)

                # Redirect to result page — shows validation errors
                return redirect('imports:result', pk=log.pk)

            # ── Phase 2: Import ──────────────────────────────────
            log = import_workbook(
                path=tmp_path,
                log=log,           # pass existing log to update it
                uploaded_by=request.user,
            )
            os.unlink(tmp_path)
            return redirect('imports:result', pk=log.pk)

        except Exception as e:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            log.status    = 'failed'
            log.error_log = f'Unexpected error: {e}'
            log.save()
            return redirect('imports:result', pk=log.pk)

    context = {
        'page_title':  'Import Excel Workbook',
        'recent_logs': recent_logs,
        'sheets_info': sheets_info,
    }
    return render(request, 'imports/upload.html', context)


@login_required
def import_result(request, pk):
    log = get_object_or_404(ImportLog, pk=pk)

    errors = []
    if log.error_log:
        errors = [
            e.strip()
            for e in log.error_log.split('\n')
            if e.strip()
        ]

    context = {
        'page_title': f'Import Result — {log.file_name}',
        'log':         log,
        'errors':      errors,
        'error_count': len(errors),
    }
    return render(request, 'imports/result.html', context)


@login_required
def import_history(request):
    logs = ImportLog.objects.order_by('-created_at')
    context = {
        'page_title': 'Import History',
        'logs':       logs,
    }
    return render(request, 'imports/history.html', context)

@login_required
def upload_sheet(request, sheet_key):
    from .services import (
        SHEET_REGISTRY, validate_single_sheet, import_single_sheet
    )

    if sheet_key not in SHEET_REGISTRY:
        messages.error(request, f'Unknown import type: {sheet_key}')
        return redirect('imports:upload')

    entry = SHEET_REGISTRY[sheet_key]
    label = entry['label']

    if request.method == 'POST':
        uploaded_file = request.FILES.get('sheet_file')

        if not uploaded_file:
            messages.error(request, 'Please select a file.')
            return redirect('imports:sheet', sheet_key=sheet_key)

        if not uploaded_file.name.endswith(('.xlsx', '.xls')):
            messages.error(request,
                f'"{uploaded_file.name}" is not valid.')
            return redirect('imports:sheet', sheet_key=sheet_key)

        # Create log immediately
        log = ImportLog.objects.create(
            file_name=uploaded_file.name,
            uploaded_by=request.user,
            status='pending',
            import_type=sheet_key,
        )

        suffix = os.path.splitext(uploaded_file.name)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(uploaded_file, tmp)
            tmp_path = tmp.name

        try:
            validation = validate_single_sheet(tmp_path, sheet_key)

            if not validation['valid']:
                error_lines = [
                    f"[{e['sheet']}] Row {e['row']}: {e['message']}"
                    for e in validation['errors']
                ]
                log.status                 = 'validation_failed'
                log.validation_error_count = validation['error_count']
                log.error_log              = '\n'.join(error_lines)
                log.save()

                os.unlink(tmp_path)
                return redirect('imports:result', pk=log.pk)

            log = import_single_sheet(
                path=tmp_path,
                sheet_key=sheet_key,
                log=log,
                uploaded_by=request.user,
            )
            os.unlink(tmp_path)
            return redirect('imports:result', pk=log.pk)

        except Exception as e:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            log.status    = 'failed'
            log.error_log = f'Unexpected error: {e}'
            log.save()
            return redirect('imports:result', pk=log.pk)

    context = {
        'page_title':  f'Import {label}',
        'sheet_key':   sheet_key,
        'label':       label,
        'entry':       entry,
    }
    return render(request, 'imports/upload_sheet.html', context)