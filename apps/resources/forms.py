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

        # ── Category dropdown (unchanged) ───────────────────────────
        if categories is None:
            from .models import ResourceCategory
            categories = ResourceCategory.get_available_names()

        category_choices = [('', '— Select Category —')] + [
            (name, name) for name in categories
        ]
        self.fields['category'].widget = forms.Select(
            choices=category_choices,
            attrs={'class': 'form-select'}
        )
        self.fields['category'].required = True

        # ── Unit dropdown ────────────────────────────────────────────
        # Data-driven, same idea as Category: every distinct unit
        # already in use across Resources, alphabetical with
        # digit/symbol-led units sorted last, plus a "+ Add new
        # unit…" escape hatch (handled in clean_unit below) so a
        # genuinely new unit doesn't require a Django Admin trip.
        # .order_by('unit') here is required, not cosmetic: Resource's
        # default Meta.ordering (['category', 'resource_name']) leaks
        # into the SQL ORDER BY even for this values_list() query,
        # which breaks .distinct() on SQLite — you get one row per
        # distinct (unit, category, resource_name) combo instead of
        # one row per distinct unit. Overriding the ordering here
        # fixes it.
        existing_units = list(
            Resource.objects.exclude(unit='')
            .values_list('unit', flat=True)
            .order_by('unit')
            .distinct()
        )

        def _unit_sort_key(name):
            first_char = name.strip()[:1]
            return (0, name.lower()) if first_char.isalpha() else (1, name.lower())

        existing_units.sort(key=_unit_sort_key)

        unit_choices = [('', '— Select Unit —')] + [
            (u, u) for u in existing_units
        ] + [('__new__', '+ Add new unit…')]

        self.fields['unit'].widget = forms.Select(
            choices=unit_choices,
            attrs={'class': 'form-select', 'id': 'id_unit'}
        )
        self.fields['unit'].required = True

        # Override rate is never required
        self.fields['manual_override_rate'].required = False
        self.fields['override_reason'].required = False

    def clean_unit(self):
        """
        Resolves the "+ Add new unit…" option: if that was selected,
        pull the actual typed value from the parallel 'new_unit' text
        field instead (rendered/shown only when '__new__' is picked —
        see templates/resources/form.html for the toggle JS).
        """
        unit = self.cleaned_data.get('unit', '')

        if unit == '__new__':
            new_unit = (self.data.get('new_unit') or '').strip()
            if not new_unit:
                raise forms.ValidationError(
                    'Please type the new unit, or pick an existing one.'
                )
            return new_unit

        return unit