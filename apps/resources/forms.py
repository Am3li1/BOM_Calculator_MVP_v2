# apps/resources/forms.py

from django import forms
from .models import Resource


class ResourceForm(forms.ModelForm):
    """
    ModelForm for creating and editing Resources.

    The category field is built dynamically from the ResourceCategory
    table rather than hardcoded choices. This means administrators can
    add, rename, or remove categories through Django Admin without
    any code changes.

    The view passes a 'categories' queryset to __init__ so the
    dropdown always reflects the current database state.
    """

    class Meta:
        model = Resource
        fields = ['resource_name', 'category', 'unit', 'rate', 'active']

        widgets = {
            'resource_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Teak Wood, Carpenter',
            }),
            # category widget is set dynamically in __init__
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
        }

        labels = {
            'resource_name': 'Resource Name',
            'category':      'Category',
            'unit':          'Unit of Measurement',
            'rate':          'Rate per Unit (₹)',
            'active':        'Active',
        }

        help_texts = {
            'rate': (
                'Changing this rate will instantly update '
                'all product costs.'
            ),
            'active': (
                'Inactive resources are hidden from BOM selection.'
            ),
        }

    def __init__(self, *args, categories=None, **kwargs):
        """
        Accepts an optional 'categories' queryset from the view.

        Why we do this here instead of in Meta.widgets:
        Meta.widgets is evaluated once at class definition time —
        it cannot read from the database dynamically.
        __init__ runs every time the form is instantiated, so it
        always gets fresh data from the database.
        """
        super().__init__(*args, **kwargs)

        if categories is not None:
            # Build (value, label) pairs for the select dropdown.
            # value and label are both the category name string
            # because we store the name directly on Resource.category.
            category_choices = [('', '— Select Category —')] + [
                (cat.name, cat.name) for cat in categories
            ]
        else:
            # Fallback: if no categories passed, build from
            # whatever is currently in the Resource table.
            # This prevents a blank dropdown if the view
            # forgets to pass categories.
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
        # Required so the empty first option triggers validation
        self.fields['category'].required = True