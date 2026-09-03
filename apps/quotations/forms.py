# apps/quotations/forms.py
from django import forms
from django.forms import inlineformset_factory

from .models import Customer, Quotation, QuotationItem, MarkupTier


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'phone_number', 'email', 'address', 'state', 'gst_number', 'customer_type', 'tally_ledger_name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'state': forms.TextInput(attrs={'class': 'form-control'}),
            'gst_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 33AAQPA5503L1ZT'}),
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'tally_ledger_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean_gst_number(self):
        gstin = self.cleaned_data['gst_number'].strip().upper()
        if len(gstin) != 15:
            raise forms.ValidationError("GSTIN must be exactly 15 characters.")
        return gstin


class QuotationItemForm(forms.ModelForm):
    class Meta:
        model = QuotationItem
        # Only user-entered fields go in the form. base_cost, hsn_code,
        # gst_rate, tax_type, cgst/sgst/igst_amount and line_total are all
        # computed and snapshotted server-side in the view — never trust
        # the client for these, since they determine the printed tax figures.
        fields = ['product', 'quantity', 'markup_tier']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'markup_tier': forms.Select(attrs={'class': 'form-select markup-tier-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['markup_tier'].queryset = MarkupTier.objects.filter(active=True)


# Formset for adding multiple product lines to one quotation.
# instance is set to an unsaved Quotation() on GET, and reassigned to the
# real saved Quotation inside transaction.atomic() in the view on POST.
QuotationItemFormSet = inlineformset_factory(
    Quotation,
    QuotationItem,
    form=QuotationItemForm,
    extra=1,
    can_delete=True,
)