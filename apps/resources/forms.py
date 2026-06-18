# apps/resources/forms.py

from django import forms
from .models import Resource


class ResourceForm(forms.ModelForm):
    """
    ModelForm automatically generates form fields
    from the Resource model. We just customise the
    widgets (HTML input types) and labels.
    """

    class Meta:
        model = Resource
        fields = ['resource_name', 'category', 'unit', 'rate', 'active']

        widgets = {
            'resource_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Teak Wood, Labour Polishing',
            }),
            'category': forms.Select(attrs={
                'class': 'form-select',
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. SFT, CFT, NOS, KG, RFT',
            }),
            'rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

        labels = {
            'resource_name': 'Resource Name',
            'category': 'Category',
            'unit': 'Unit of Measurement',
            'rate': 'Rate per Unit (₹)',
            'active': 'Active',
        }

        help_texts = {
            'rate': 'Changing this rate will instantly update all product costs.',
            'active': 'Inactive resources are hidden from BOM selection.',
        }