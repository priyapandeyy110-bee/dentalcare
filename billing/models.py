from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from accounts.models import PatientProfile
from appointments.models import Appointment
from records.models import Treatment


class BillStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    UNPAID = "UNPAID", "Unpaid"
    PARTIAL = "PARTIAL", "Partially paid"
    PAID = "PAID", "Paid"
    CANCELLED = "CANCELLED", "Cancelled"


class Bill(models.Model):
    """Invoice for consultation and treatment charges (synopsis module 6)."""

    invoice_number = models.CharField(max_length=24, unique=True, editable=False)
    patient = models.ForeignKey(PatientProfile, on_delete=models.CASCADE, related_name="bills")
    appointment = models.ForeignKey(
        Appointment, on_delete=models.SET_NULL, null=True, blank=True, related_name="bills"
    )
    treatment = models.ForeignKey(
        Treatment, on_delete=models.SET_NULL, null=True, blank=True, related_name="bills"
    )
    issued_on = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=BillStatus.choices, default=BillStatus.UNPAID)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="bills_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issued_on", "-created_at"]

    def __str__(self):
        return "%s - %s" % (self.invoice_number, self.patient.user.display_name)

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_invoice_number():
        prefix = "INV-%s-" % timezone.now().strftime("%Y%m")
        last = Bill.objects.filter(invoice_number__startswith=prefix).order_by("-invoice_number").first()
        sequence = int(last.invoice_number.rsplit("-", 1)[1]) + 1 if last else 1
        return "%s%04d" % (prefix, sequence)

    def get_absolute_url(self):
        return reverse("billing:detail", args=[self.pk])

    @property
    def subtotal(self):
        total = self.items.aggregate(
            value=Sum(models.F("unit_price") * models.F("quantity"), output_field=models.DecimalField())
        )["value"]
        return Decimal(total or 0)

    @property
    def tax_amount(self):
        taxable = max(self.subtotal - self.discount, Decimal("0"))
        return (taxable * self.tax_percent / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def total(self):
        return max(self.subtotal - self.discount + self.tax_amount, Decimal("0"))

    @property
    def amount_paid(self):
        return Decimal(self.payments.aggregate(value=Sum("amount"))["value"] or 0)

    @property
    def balance_due(self):
        return max(self.total - self.amount_paid, Decimal("0"))

    @property
    def status_css(self):
        return {
            BillStatus.DRAFT: "secondary",
            BillStatus.UNPAID: "danger",
            BillStatus.PARTIAL: "warning",
            BillStatus.PAID: "success",
            BillStatus.CANCELLED: "secondary",
        }.get(self.status, "secondary")

    def recalculate_status(self, commit=True):
        """Keep ``status`` in step with recorded payments."""
        if self.status == BillStatus.CANCELLED:
            return self.status
        paid = self.amount_paid
        if paid <= 0:
            self.status = BillStatus.UNPAID
        elif paid < self.total:
            self.status = BillStatus.PARTIAL
        else:
            self.status = BillStatus.PAID
        if commit:
            self.save(update_fields=["status", "updated_at"])
        return self.status

    def can_be_viewed_by(self, user):
        if user.is_superuser or user.is_admin_role or user.is_dentist:
            return True
        return self.patient.user_id == user.id


class BillItem(models.Model):
    """A charge line: consultation, procedure, material or lab work."""

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=200)
    quantity = models.PositiveSmallIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return "%s x%s" % (self.description, self.quantity)

    @property
    def line_total(self):
        return Decimal(self.unit_price) * self.quantity


class PaymentMethod(models.TextChoices):
    CASH = "CASH", "Cash"
    CARD = "CARD", "Card"
    UPI = "UPI", "UPI"
    NET_BANKING = "NETBANK", "Net banking"
    INSURANCE = "INSURANCE", "Insurance"


class Payment(models.Model):
    """Money received against a bill."""

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(
        max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.CASH
    )
    reference = models.CharField(max_length=80, blank=True)
    paid_on = models.DateField(default=timezone.localdate)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payments_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_on", "-created_at"]

    def __str__(self):
        return "%s on %s (%s)" % (self.amount, self.bill.invoice_number, self.get_method_display())
