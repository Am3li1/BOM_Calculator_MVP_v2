from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def costing_list(request):
    return render(request, 'costing/list.html', {'page_title': 'Cost Sheets'})