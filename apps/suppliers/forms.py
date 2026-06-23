# apps/suppliers/forms.py

from django import forms
from .models import Supplier


class SupplierForm(forms.ModelForm):
    """Form for creating and editing suppliers."""

    class Meta:
        model = Supplier
        fields = ['supplier_name', 'phone_number', 'gst_number', 'active']

        widgets = {
            'supplier_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. ABC Metals Pvt Ltd',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. +91 98765 43210',
            }),
            'gst_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 29ABCDE1234F1Z5',
            }),
            'active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

        labels = {
            'supplier_name': 'Supplier Name',
            'phone_number':  'Phone Number',
            'gst_number':    'GST Number',
            'active':        'Active',
        }