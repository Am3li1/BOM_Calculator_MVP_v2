from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def upload(request):
    return render(request, 'imports/upload.html', {'page_title': 'Import Excel'})