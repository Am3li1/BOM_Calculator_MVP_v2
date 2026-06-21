# apps/imports/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import ImportLog
from .services import import_workbook


@login_required
def upload(request):
    """
    GET:  Shows the file upload form.
    POST: Receives the uploaded Excel file, runs the import service,
          redirects to the result page.
    """
    # Show previous import history so users can see what was imported before
    recent_logs = ImportLog.objects.order_by('-created_at')[:10]

    if request.method == 'POST':
        uploaded_file = request.FILES.get('workbook')

        # Validate that a file was actually attached
        if not uploaded_file:
            messages.error(request, 'Please select an Excel file to upload.')
            return redirect('imports:upload')

        # Validate file extension
        if not uploaded_file.name.endswith(('.xlsx', '.xls')):
            messages.error(
                request,
                f'"{uploaded_file.name}" is not a valid Excel file. '
                f'Please upload a .xlsx or .xls file.'
            )
            return redirect('imports:upload')

        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024  # 10 MB in bytes
        if uploaded_file.size > max_size:
            messages.error(
                request,
                f'File is too large ({uploaded_file.size // 1024 // 1024}MB). '
                f'Maximum allowed size is 10MB.'
            )
            return redirect('imports:upload')

        # Run the import service
        # This is where all the Excel reading and database writing happens
        log, results = import_workbook(
            file_obj=uploaded_file,
            uploaded_by=request.user,
        )

        # Redirect to the result page, passing the log ID
        return redirect('imports:result', pk=log.pk)

    context = {
        'page_title': 'Import Excel Workbook',
        'recent_logs': recent_logs,
        'sheets_info': [
            ('Resource',      'Materials, rates, categories'),
            ('Products',      'Product names'),
            ('BOM',           'Bill of materials per product'),
            ('Wood, Ply MDF', 'Dimension entries per product'),
        ],
    }
    return render(request, 'imports/upload.html', context)


@login_required
def import_result(request, pk):
    """
    Shows the result of a specific import run.
    The ImportLog record holds all the counts and errors.
    """
    log = get_object_or_404(ImportLog, pk=pk)

    # Parse errors from the log's text field into a list
    # so the template can loop over them cleanly
    errors = []
    if log.error_log:
        errors = [
            e.strip()
            for e in log.error_log.split('\n')
            if e.strip()
        ]

    context = {
        'page_title': f'Import Result — {log.file_name}',
        'log': log,
        'errors': errors,
        'error_count': len(errors),
    }
    return render(request, 'imports/result.html', context)


@login_required
def import_history(request):
    """
    Shows all past import logs.
    """
    logs = ImportLog.objects.order_by('-created_at')

    context = {
        'page_title': 'Import History',
        'logs': logs,
    }
    return render(request, 'imports/history.html', context)