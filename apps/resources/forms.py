# apps/resources/forms.py
from django import forms
from .models import Resource, UNIT_CHOICES


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
        # Full-word labels from the canonical UNIT_CHOICES list in
        # models.py (shared with the BOM Dimensions unit dropdowns —
        # single source of truth, see the comment there). This is no
        # longer data-driven off Resource.unit: a fixed list reads
        # more clearly than raw codes like "cft"/"sqft", and it means
        # a resource with a legacy/one-off unit value already in the
        # database (typos, old free-text entries, etc.) doesn't leak
        # into everyone else's dropdown. The stored value on any such
        # resource is left exactly as-is; editing that one resource
        # just won't show a pre-selected match here — a "+ Add new
        # unit…" escape hatch (handled in clean_unit below) covers a
        # genuinely new unit without a Django Admin trip.
        #
        # (The old version queried distinct Resource.unit values with
        # an explicit .order_by('unit') before .distinct() — that
        # order_by was working around Resource's default Meta.ordering
        # leaking into the SQL and breaking .distinct() on SQLite.
        # That workaround is no longer needed now that this dropdown
        # doesn't query Resource at all.)
        unit_choices = [('', '— Select Unit —')] + list(UNIT_CHOICES) + [
            ('__new__', '+ Add new unit…')
        ]

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