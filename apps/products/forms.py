# apps/products/forms.py

from django import forms
from .models import Product


class ProductForm(forms.ModelForm):

    class Meta:
        model = Product
        # product_code is intentionally NOT in this list — it's
        # auto-generated from product_name in the view (see
        # apps/products/views.py: _generate_unique_product_code).
        # Users never see or type it.
        fields = ['product_name', 'hsn_code', 'gst_rate', 'active']

        widgets = {
            'product_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 3-Door Wardrobe with Mirror',
            }),
            'hsn_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 9403',
            }),
            'gst_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'e.g. 18.00',
            }),
            'active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

        labels = {
            'product_name': 'Product Name',
            'hsn_code': 'HSN Code',
            'gst_rate': 'GST Rate (%)',
            'active': 'Active',
        }

        help_texts = {
            'active': 'Inactive products are hidden from cost sheet views.',
            'gst_rate': 'Used for tax calculation on quotations.',
        }