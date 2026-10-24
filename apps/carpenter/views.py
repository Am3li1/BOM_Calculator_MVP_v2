# apps/carpenter/views.py
#
# Carpenter area — the only part of the app the Carpenter role can reach.
# Nothing here may expose rates, costs, suppliers or cost sheets
# (CLAUDE.md Security rule 3). Staged BOM entry (BOMSubmission /
# SubmissionLine) will live in this app; for now there is only a
# landing page.

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.core.decorators import carpenter_required


@login_required
@carpenter_required
def home(request):
    return render(request, 'carpenter/home.html', {
        'page_title': 'Carpenter',
    })
