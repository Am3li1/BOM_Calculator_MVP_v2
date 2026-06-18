from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def bom_list(request):
    return render(request, 'bom/list.html', {'page_title': 'BOM'})