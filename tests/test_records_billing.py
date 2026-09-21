"""Clinical records and billing: totals, payments, permissions and workflow."""

from decimal import Decimal

import pytest
from django.urls import reverse

from appointments.models import AppointmentStatus
from billing.models import Bill, BillItem, BillStatus, Payment, PaymentMethod
from records.models import Prescription, Treatment

pytestmark = pytest.mark.django_db


# --- Invoice arithmetic ----------------------------------------------------

def test_totals_add_up(bill):
    BillItem.objects.create(
        bill=bill, description="Consultation", quantity=1, unit_price=Decimal("500")
    )
    assert bill.subtotal == Decimal("2700")
    assert bill.total == Decimal("2700")
    assert bill.balance_due == Decimal("2700")
    assert bill.amount_paid == Decimal("0")


def test_quantity_multiplies_the_line(bill):
    BillItem.objects.create(
        bill=bill, description="X-ray", quantity=3, unit_price=Decimal("200")
    )
    assert bill.subtotal == Decimal("2800")


def test_discount_and_tax_are_applied_in_order(bill):
    bill.discount = Decimal("200")
    bill.tax_percent = Decimal("10")
    bill.save()

    # (2200 - 200) * 10% = 200 tax, total 2200
    assert bill.tax_amount == Decimal("200.00")
    assert bill.total == Decimal("2200.00")


def test_partial_payment_sets_partial_status(bill):
    Payment.objects.create(
        bill=bill, amount=Decimal("1000"), method=PaymentMethod.UPI
    )
    bill.recalculate_status()
    assert bill.status == BillStatus.PARTIAL
    assert bill.balance_due == Decimal("1200")


def test_full_payment_sets_paid_status(bill):
    Payment.objects.create(
        bill=bill, amount=bill.total, method=PaymentMethod.CASH
    )
    bill.recalculate_status()
    assert bill.status == BillStatus.PAID
    assert bill.balance_due == Decimal("0")


def test_balance_never_goes_negative(bill):
    Payment.objects.create(bill=bill, amount=Decimal("5000"))
    assert bill.balance_due == Decimal("0")


def test_cancelled_invoice_keeps_its_status(bill):
    bill.status = BillStatus.CANCELLED
    bill.save()
    Payment.objects.create(bill=bill, amount=Decimal("100"))
    assert bill.recalculate_status() == BillStatus.CANCELLED


def test_invoice_numbers_are_unique(patient):
    first = Bill.objects.create(patient=patient)
    second = Bill.objects.create(patient=patient)
    assert first.invoice_number != second.invoice_number
    assert first.invoice_number.startswith("INV-")


# --- Billing views ---------------------------------------------------------

def test_admin_records_a_payment(admin_client_, bill):
    response = admin_client_.post(
        reverse("billing:detail", args=[bill.pk]),
        {
            "amount": "1000",
            "method": PaymentMethod.CASH,
            "reference": "",
            "paid_on": bill.issued_on.isoformat(),
        },
        follow=True,
    )
    assert response.status_code == 200
    bill.refresh_from_db()
    assert bill.amount_paid == Decimal("1000")
    assert bill.status == BillStatus.PARTIAL
    assert bill.patient.user.notifications.filter(notification_type="PAYMENT").exists()


def test_overpayment_is_rejected(admin_client_, bill):
    response = admin_client_.post(
        reverse("billing:detail", args=[bill.pk]),
        {
            "amount": "99999",
            "method": PaymentMethod.CASH,
            "paid_on": bill.issued_on.isoformat(),
        },
    )
    assert response.status_code == 200
    assert b"more than the outstanding balance" in response.content
    assert bill.amount_paid == Decimal("0")


def test_patient_cannot_record_a_payment(patient_client, bill):
    response = patient_client.post(
        reverse("billing:detail", args=[bill.pk]),
        {"amount": "500", "method": PaymentMethod.CASH, "paid_on": bill.issued_on.isoformat()},
    )
    # The form is not offered to patients, so nothing is recorded.
    assert bill.amount_paid == Decimal("0")
    assert response.status_code == 200


def test_patient_cannot_see_another_patients_invoice(
    patient_client, bill, django_user_model
):
    from accounts.models import PatientProfile, Role

    other = django_user_model.objects.create_user(
        username="other2", password="x", role=Role.PATIENT
    )
    bill.patient = PatientProfile.objects.create(user=other)
    bill.save()

    response = patient_client.get(reverse("billing:detail", args=[bill.pk]))
    assert response.status_code == 403


def test_patient_cannot_create_an_invoice(patient_client, patient):
    response = patient_client.get(reverse("billing:create", args=[patient.pk]))
    assert response.status_code == 403


def test_admin_creates_an_invoice_from_a_treatment(admin_client_, patient, treatment):
    url = "%s?treatment=%s" % (reverse("billing:create", args=[patient.pk]), treatment.pk)
    response = admin_client_.post(
        url,
        {
            "issued_on": treatment.treatment_date.isoformat(),
            "due_date": "",
            "discount": "0",
            "tax_percent": "0",
            "status": BillStatus.UNPAID,
            "notes": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-description": "Composite filling",
            "items-0-quantity": "1",
            "items-0-unit_price": "2200",
        },
        follow=True,
    )
    assert response.status_code == 200
    bill = Bill.objects.filter(treatment=treatment).latest("pk")
    assert bill.total == Decimal("2200")
    assert bill.patient.user.notifications.filter(notification_type="BILL").exists()


# --- Treatment records -----------------------------------------------------

def test_dentist_records_a_treatment_and_completes_the_appointment(
    dentist_client, patient, dentist, appointment
):
    url = "%s?appointment=%s" % (
        reverse("records:treatment_create", args=[patient.pk]), appointment.pk
    )
    response = dentist_client.post(
        url,
        {
            "treatment_date": appointment.scheduled_for.date().isoformat(),
            "chief_complaint": "Pain on biting",
            "diagnosis": "Cracked cusp on 46.",
            "procedure": "FILLING",
            "tooth_region": "LR",
            "tooth_numbers": "46",
            "treatment_notes": "Composite placed.",
            "status": "COMPLETED",
            "cost": "2200",
            "follow_up_date": "",
            "follow_up_instructions": "",
        },
        follow=True,
    )

    assert response.status_code == 200
    treatment = Treatment.objects.get(appointment=appointment)
    assert treatment.dentist == dentist

    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.COMPLETED

    patient.refresh_from_db()
    assert patient.last_dental_visit == treatment.treatment_date
    assert patient.user.notifications.filter(notification_type="TREATMENT").exists()


def test_follow_up_cannot_precede_the_treatment(dentist_client, patient):
    response = dentist_client.post(
        reverse("records:treatment_create", args=[patient.pk]),
        {
            "treatment_date": "2026-05-10",
            "diagnosis": "Test",
            "procedure": "CONSULT",
            "tooth_region": "NA",
            "status": "COMPLETED",
            "cost": "0",
            "follow_up_date": "2026-05-01",
        },
    )
    assert response.status_code == 200
    assert b"cannot be before the treatment date" in response.content
    assert not Treatment.objects.exists()


def test_patient_cannot_record_a_treatment(patient_client, patient):
    response = patient_client.get(reverse("records:treatment_create", args=[patient.pk]))
    assert response.status_code == 403


def test_dentist_issues_a_prescription(dentist_client, patient, treatment):
    url = "%s?treatment=%s" % (
        reverse("records:prescription_create", args=[patient.pk]), treatment.pk
    )
    response = dentist_client.post(
        url,
        {
            "issued_on": treatment.treatment_date.isoformat(),
            "advice": "Soft diet for two days.",
            "items-TOTAL_FORMS": "2",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-medicine_name": "Amoxicillin",
            "items-0-dosage": "500 mg",
            "items-0-frequency": "Three times daily",
            "items-0-duration": "5 days",
            "items-0-instructions": "Finish the course.",
            "items-1-medicine_name": "Ibuprofen",
            "items-1-dosage": "400 mg",
            "items-1-frequency": "Twice daily",
            "items-1-duration": "3 days",
            "items-1-instructions": "",
        },
        follow=True,
    )

    assert response.status_code == 200
    prescription = Prescription.objects.get()
    assert prescription.items.count() == 2
    assert prescription.patient == patient
    assert patient.user.notifications.filter(notification_type="PRESCRIPTION").exists()


def test_patient_sees_only_their_own_records(patient_client, treatment, django_user_model):
    from accounts.models import PatientProfile, Role

    other = django_user_model.objects.create_user(
        username="other3", password="x", role=Role.PATIENT
    )
    other_patient = PatientProfile.objects.create(user=other)
    Treatment.objects.create(
        patient=other_patient, dentist=treatment.dentist,
        diagnosis="Someone else record", procedure="CONSULT",
    )

    response = patient_client.get(reverse("records:treatment_list"))
    assert response.status_code == 200
    assert b"Someone else record" not in response.content


# --- Reminders -------------------------------------------------------------

def test_send_reminders_is_idempotent(appointment, settings):
    from django.core.management import call_command
    from io import StringIO

    appointment.scheduled_for = appointment.scheduled_for.replace(microsecond=0)
    appointment.save()

    out = StringIO()
    call_command("send_reminders", "--hours", "72", "--no-email", stdout=out)
    assert appointment.patient.user.notifications.filter(
        notification_type="APT_REMINDER"
    ).count() == 1

    # Running it again must not send a second reminder.
    call_command("send_reminders", "--hours", "72", "--no-email", stdout=out)
    assert appointment.patient.user.notifications.filter(
        notification_type="APT_REMINDER"
    ).count() == 1


def test_dry_run_sends_nothing(appointment):
    from django.core.management import call_command
    from io import StringIO

    call_command("send_reminders", "--hours", "72", "--dry-run", stdout=StringIO())
    assert not appointment.patient.user.notifications.filter(
        notification_type="APT_REMINDER"
    ).exists()
    appointment.refresh_from_db()
    assert appointment.reminder_sent_at is None
