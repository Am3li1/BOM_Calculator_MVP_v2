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
    """
    GET:  Show upload form.
    POST: Validate file → if valid, import → redirect to result.
          If invalid → show validation error report immediately.
          Never imports partial data.
    """
    recent_logs = ImportLog.objects.order_by('-created_at')[:10]

    sheets_info = [
        ('Resource',      'Materials, rates, categories'),
        ('Products',      'Product names'),
        ('BOM',           'Bill of materials per product'),
        ('Wood, Ply MDF', 'Dimension entries per product'),
    ]

    if request.method == 'POST':
        uploaded_file = request.FILES.get('workbook')

        # ── Basic file checks ────────────────────────────────────
        if not uploaded_file:
            messages.error(request, 'Please select a file.')
            return redirect('imports:upload')

        if not uploaded_file.name.endswith(('.xlsx', '.xls')):
            messages.error(
                request,
                f'"{uploaded_file.name}" is not a valid Excel file.'
            )
            return redirect('imports:upload')

        max_size = 10 * 1024 * 1024
        if uploaded_file.size > max_size:
            messages.error(request,
                f'File too large '
                f'({uploaded_file.size // 1024 // 1024}MB). '
                f'Maximum is 10MB.')
            return redirect('imports:upload')

        # ── Save to temp file so we can read multiple times ──────
        suffix = os.path.splitext(uploaded_file.name)[1]
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix
        )
        shutil.copyfileobj(uploaded_file, tmp)
        tmp.close()
        tmp_path = tmp.name

        try:
            # ── PHASE 1: Validate ────────────────────────────────
            validation = validate_workbook(tmp_path)

            if not validation['valid']:
                # Validation failed — show errors, import NOTHING
                os.unlink(tmp_path)
                context = {
                    'page_title':      'Import Failed — Validation Errors',
                    'recent_logs':     recent_logs,
                    'sheets_info':     sheets_info,
                    'validation':      validation,
                    'filename':        uploaded_file.name,
                    'show_errors':     True,
                }
                return render(
                    request,
                    'imports/upload.html',
                    context
                )

            # ── PHASE 2: Import (validation passed) ──────────────
            # Reset the file pointer — we need to pass the name
            # to the log, but the actual reading uses tmp_path
            log = import_workbook(
                path=tmp_path,
                file_obj=uploaded_file,
                uploaded_by=request.user,
            )
            os.unlink(tmp_path)

            return redirect('imports:result', pk=log.pk)

        except Exception as e:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
            messages.error(
                request,
                f'Unexpected error: {e}'
            )
            return redirect('imports:upload')

    context = {
        'page_title':  'Import Excel Workbook',
        'recent_logs': recent_logs,
        'sheets_info': sheets_info,
        'show_errors': False,
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