from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory

from accounts.forms import BootstrapMixin

from .models import Bill, BillItem, Payment


class BillForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Bill
        fields = ("issued_on", "due_date", "discount", "tax_percent", "status", "notes")
        widgets = {
            "issued_on": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def clean(self):
        cleaned = super().clean()
        issued = cleaned.get("issued_on")
        due = cleaned.get("due_date")
        if issued and due and due < issued:
            self.add_error("due_date", "The due date cannot be before the issue date.")
        if (cleaned.get("discount") or 0) < 0:
            self.add_error("discount", "Discount cannot be negative.")
        return cleaned


class BillItemForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = BillItem
        fields = ("description", "quantity", "unit_price")


BillItemFormSet = inlineformset_factory(
    Bill,
    BillItem,
    form=BillItemForm,
    extra=3,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class PaymentForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ("amount", "method", "reference", "paid_on")
        widgets = {"paid_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        self.bill = kwargs.pop("bill", None)
        super().__init__(*args, **kwargs)
        if self.bill:
            self.fields["amount"].initial = self.bill.balance_due
            self.fields["amount"].help_text = "Balance due: %s" % self.bill.balance_due

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        if self.bill and amount > self.bill.balance_due + Decimal("0.01"):
            raise forms.ValidationError(
                "That is more than the outstanding balance of %s." % self.bill.balance_due
            )
        return amount
