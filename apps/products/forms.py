# apps/products/forms.py

from django import forms
from .models import Product


class ProductForm(forms.ModelForm):

    class Meta:
        model = Product
        fields = ['product_name', 'product_code', 'active']

        widgets = {
            'product_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 3-Door Wardrobe with Mirror',
            }),
            'product_code': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. WRD-001',
            }),
            'active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }

        labels = {
            'product_name': 'Product Name',
            'product_code': 'Product Code',
            'active': 'Active',
        }

        help_texts = {
            'product_code': 'Must be unique. Used as identifier across the system.',
            'active': 'Inactive products are hidden from cost sheet views.',
        }

    def clean_product_code(self):
        """
        Custom validation for product_code.

        Django's default unique check finds ALL rows including
        soft-deleted ones (is_deleted=True), which blocks re-use
        of a code after deletion.

        This override checks uniqueness only among ACTIVE (non-deleted)
        products, and also handles the edit case (exclude self).
        """
        code = self.cleaned_data.get('product_code', '').strip().upper()

        # Build a queryset of conflicting records
        # — exclude soft-deleted products
        # — exclude the current instance when editing (self.instance.pk)
        qs = Product.objects.filter(
            product_code=code,
            is_deleted=False
        )

        # If we're editing an existing product, exclude it from the check
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError(
                f'An active product with code "{code}" already exists.'
            )

        return code