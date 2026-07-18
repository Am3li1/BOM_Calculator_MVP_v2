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
            'formula_expression',
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
            'formula_expression': forms.TextInput(attrs={
                'class': 'form-control font-monospace',
                'placeholder': 'e.g. width_in * breadth_in * length_ft * pieces / 144',
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
            'formula_expression':   'Custom Formula (optional)',
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
            'formula_expression': (
                'Overrides the built-in Material Type formula for this '
                'resource specifically. Leave blank to use the default '
                'Solid Wood / Sheet / Other formula.'
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
        self.fields['formula_expression'].required = False

    def clean_formula_expression(self):
        """
        Validates the formula at save time using dummy dimension
        values — catches typos/syntax errors/unknown variables
        immediately, rather than the first time someone views a cost
        sheet using this resource.
        """
        expr = self.cleaned_data.get('formula_expression', '').strip()
        if not expr:
            return expr

        from apps.core.safe_eval import evaluate_formula, FormulaError

        dummy_variables = {
            'width': 10, 'breadth': 10, 'height': 10, 'length': 10, 'pieces': 1,
            'width_in': 10, 'breadth_in': 10, 'height_in': 10, 'length_in': 10,
            'width_ft': 1, 'breadth_ft': 1, 'height_ft': 1, 'length_ft': 1,
        }
        try:
            evaluate_formula(expr, dummy_variables)
        except FormulaError as e:
            raise forms.ValidationError(str(e))

        return expr