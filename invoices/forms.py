from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from .models import BusinessProfile, Client, Invoice, InvoiceItem


class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = BusinessProfile
        fields = ['business_name', 'logo', 'address', 'city', 'state', 'zip_code', 'country', 'email', 'phone']
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Business name (required)'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Street, City, State, ZIP'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'zip_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ZIP / Postal code'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Country'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contact@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone (optional)'}),
        }


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['name', 'email', 'phone', 'address']


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['client', 'client_name', 'client_email', 'client_phone', 'client_address', 'currency', 'invoice_number', 'invoice_date', 'due_date', 'status', 'tax_rate', 'discount_amount', 'payment_terms', 'notes']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'currency': forms.TextInput(attrs={'class': 'form-control', 'style': 'width:100px'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'client_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'client_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'client_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'tax_rate': forms.NumberInput(attrs={'id': 'id_tax_rate', 'step': '0.01', 'class': 'form-control'}),
            'discount_amount': forms.NumberInput(attrs={'id': 'id_discount_amount', 'step': '0.01', 'class': 'form-control'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'invoice_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'due_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'payment_terms': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        # Accept `user` kwarg to filter client queryset
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['client'].queryset = Client.objects.filter(user=user)
        # if instance exists, prefill snapshot fields from client if empty
        if self.instance and self.instance.pk:
            if not self.instance.client_name and self.instance.client:
                self.fields['client_name'].initial = self.instance.client.name
            if not self.instance.client_email and self.instance.client:
                self.fields['client_email'].initial = self.instance.client.email
            if not self.instance.client_phone and self.instance.client:
                self.fields['client_phone'].initial = self.instance.client.phone
            if not self.instance.client_address and self.instance.client:
                # prefer Client.address else compose from parts
                addr = self.instance.client.address
                if not addr:
                    parts = [self.instance.client.street, self.instance.client.city, self.instance.client.state, self.instance.client.zip_code, self.instance.client.country]
                    addr = ', '.join([p for p in parts if p])
                self.fields['client_address'].initial = addr


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['description', 'quantity', 'unit_price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control item-quantity'}),
            'unit_price': forms.NumberInput(attrs={'step': '0.01', 'class': 'form-control item-price'}),
        }


InvoiceItemFormSet = inlineformset_factory(Invoice, InvoiceItem, form=InvoiceItemForm, extra=1, can_delete=True)
