from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import PatientProfile
from core.permissions import admin_required
from notifications import services as notify
from records.models import Treatment

from .forms import BillForm, BillItemFormSet, PaymentForm
from .models import Bill, BillStatus


@login_required
def bill_list(request):
    queryset = Bill.objects.select_related("patient__user").prefetch_related(
        "items", "payments"
    )
    if request.user.is_patient:
        queryset = queryset.filter(patient__user=request.user)

    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if status:
        queryset = queryset.filter(status=status)
    if query:
        queryset = queryset.filter(
            Q(invoice_number__icontains=query)
            | Q(patient__user__first_name__icontains=query)
            | Q(patient__user__last_name__icontains=query)
            | Q(patient__patient_code__icontains=query)
        )

    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "billing/bill_list.html",
        {
            "page_obj": page,
            "status_choices": BillStatus.choices,
            "selected_status": status,
            "query": query,
        },
    )


@login_required
def bill_detail(request, pk):
    bill = get_object_or_404(
        Bill.objects.select_related("patient__user").prefetch_related("items", "payments"),
        pk=pk,
    )
    if not bill.can_be_viewed_by(request.user):
        raise PermissionDenied("You cannot view this invoice.")

    payment_form = None
    if request.user.is_admin_role and bill.balance_due > 0:
        payment_form = PaymentForm(request.POST or None, bill=bill)
        if request.method == "POST" and payment_form.is_valid():
            payment = payment_form.save(commit=False)
            payment.bill = bill
            payment.recorded_by = request.user
            payment.save()
            bill.recalculate_status()
            notify.payment_received(payment)
            messages.success(request, "Payment of %s recorded." % payment.amount)
            return redirect("billing:detail", pk=bill.pk)

    return render(
        request,
        "billing/bill_detail.html",
        {"bill": bill, "payment_form": payment_form},
    )


@login_required
def invoice_print(request, pk):
    """Printable invoice -- the patient can save it as a PDF from the browser."""
    bill = get_object_or_404(
        Bill.objects.select_related("patient__user").prefetch_related("items", "payments"),
        pk=pk,
    )
    if not bill.can_be_viewed_by(request.user):
        raise PermissionDenied("You cannot view this invoice.")
    return render(request, "billing/invoice_print.html", {"bill": bill})


@admin_required
def bill_create(request, patient_id):
    """Generate an invoice, pre-filled from a treatment when one is given."""
    patient = get_object_or_404(PatientProfile.objects.select_related("user"), pk=patient_id)

    treatment = None
    treatment_id = request.GET.get("treatment")
    if treatment_id:
        treatment = Treatment.objects.filter(pk=treatment_id, patient=patient).first()

    initial_items = []
    if treatment:
        initial_items.append({
            "description": "%s - %s"
            % (treatment.get_procedure_display(), treatment.treatment_date),
            "quantity": 1,
            "unit_price": treatment.cost or treatment.dentist.consultation_fee,
        })

    form = BillForm(request.POST or None)
    formset = BillItemFormSet(request.POST or None, initial=initial_items)
    if not request.POST and initial_items:
        formset.extra = len(initial_items) + 2

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            bill = form.save(commit=False)
            bill.patient = patient
            bill.treatment = treatment
            bill.appointment = treatment.appointment if treatment else None
            bill.created_by = request.user
            bill.save()
            formset.instance = bill
            formset.save()
            bill.recalculate_status()

        notify.bill_generated(bill)
        messages.success(request, "Invoice %s generated." % bill.invoice_number)
        return redirect("billing:detail", pk=bill.pk)

    return render(
        request,
        "billing/bill_form.html",
        {
            "form": form,
            "formset": formset,
            "patient": patient,
            "treatment": treatment,
            "title": "New invoice for %s" % patient.user.display_name,
        },
    )


@admin_required
def bill_edit(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    if bill.status == BillStatus.PAID:
        messages.error(request, "A fully paid invoice cannot be edited.")
        return redirect("billing:detail", pk=bill.pk)

    form = BillForm(request.POST or None, instance=bill)
    formset = BillItemFormSet(request.POST or None, instance=bill)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()
            bill.refresh_from_db()
            bill.recalculate_status()
        messages.success(request, "Invoice updated.")
        return redirect("billing:detail", pk=bill.pk)

    return render(
        request,
        "billing/bill_form.html",
        {
            "form": form,
            "formset": formset,
            "patient": bill.patient,
            "treatment": bill.treatment,
            "title": "Edit invoice %s" % bill.invoice_number,
        },
    )


@admin_required
def bill_cancel(request, pk):
    bill = get_object_or_404(Bill, pk=pk)
    if request.method == "POST":
        if bill.amount_paid > Decimal("0"):
            messages.error(
                request, "This invoice has payments against it and cannot be cancelled."
            )
        else:
            bill.status = BillStatus.CANCELLED
            bill.save(update_fields=["status", "updated_at"])
            messages.success(request, "Invoice %s cancelled." % bill.invoice_number)
    return redirect("billing:detail", pk=bill.pk)
