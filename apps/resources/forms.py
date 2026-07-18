# apps/resources/forms.py

from django import forms
from .models import Resource


class ResourceForm(forms.ModelForm):

    class Meta:
        model = Resource
        fields = [
            'resource_name',
            'category',
            'material_type',
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
            'material_type': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_material_type',
            }),
            'unit': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. cft, sqft, kg, day, nos',
                'id': 'id_unit',
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
            'material_type':        'Material Type',
            'unit':                 'Unit of Measurement',
            'rate':                 'Master Rate per Unit (₹)',
            'active':               'Active',
            'manual_override_rate': 'Override Rate',
            'override_reason':      'Override Reason',
        }

        help_texts = {
            'material_type': (
                'Drives WoodPart dimension formulas (CFT vs SFT) and '
                'auto-suggests a Unit below. Only set this for '
                'dimensional materials — leave "Other" for labour, '
                'hardware, polish, etc.'
            ),
            'rate': (
                'Fallback rate used when no supplier links exist.'
            ),
            'active': (
                'Inactive resources are hidden from BOM selection.'
            ),
        }

    def __init__(self, *args, categories=None, **kwargs):
        super().__init__(*args, **kwargs)

        if categories is None:
            from .models import ResourceCategory
            categories = ResourceCategory.get_available_names()

        # categories is a list of plain name strings (see
        # ResourceCategory.get_available_names) — merges active
        # ResourceCategory rows with any category already in use on a
        # Resource, so imported/free-text categories still show up.
        category_choices = [('', '— Select Category —')] + [
            (name, name) for name in categories
        ]

        self.fields['category'].widget = forms.Select(
            choices=category_choices,
            attrs={'class': 'form-select'}
        )
        self.fields['category'].required = True

        # Override rate is never required
        self.fields['manual_override_rate'].required = False
        self.fields['override_reason'].required = False