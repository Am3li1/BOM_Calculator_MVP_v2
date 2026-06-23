# apps/resources/forms.py

from django import forms
from .models import Resource


class ResourceForm(forms.ModelForm):

    class Meta:
        model = Resource
        fields = [
            'resource_name',
            'category',
            'unit',
            'rate',
            'active',
            'manual_override_rate',
            'override_reason',
        ]

        widgets = {
            'resource_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Teak Wood, Carpenter',
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. cft, sqft, kg, day, nos',
            }),
            'rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
            }),
            'active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
            'manual_override_rate': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Leave blank for automatic',
                'step': '0.01',
                'min': '0',
            }),
            'override_reason': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Contract rate, Quality premium',
            }),
        }

        labels = {
            'resource_name':        'Resource Name',
            'category':             'Category',
            'unit':                 'Unit of Measurement',
            'rate':                 'Master Rate per Unit (₹)',
            'active':               'Active',
            'manual_override_rate': 'Override Rate',
            'override_reason':      'Override Reason',
        }

        help_texts = {
            'rate': (
                'Fallback rate used when no supplier links exist.'
            ),
            'active': (
                'Inactive resources are hidden from BOM selection.'
            ),
        }

    def __init__(self, *args, categories=None, **kwargs):
        super().__init__(*args, **kwargs)

        if categories is not None:
            category_choices = [('', '— Select Category —')] + [
                (cat.name, cat.name) for cat in categories
            ]
        else:
            from .models import ResourceCategory
            fallback = ResourceCategory.objects.filter(
                active=True
            ).order_by('sort_order', 'name')
            category_choices = [('', '— Select Category —')] + [
                (cat.name, cat.name) for cat in fallback
            ]

        self.fields['category'].widget = forms.Select(
            choices=category_choices,
            attrs={'class': 'form-select'}
        )
        self.fields['category'].required = True

        # Override rate is never required
        self.fields['manual_override_rate'].required = False
        self.fields['override_reason'].required = False