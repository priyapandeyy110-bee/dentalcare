"""Helpers for raising in-app notifications and optionally emailing them."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone

from .models import Notification, NotificationType

logger = logging.getLogger(__name__)


def notify(recipient, notification_type, title, message, link="", email=False):
    """Create a notification. Returns the object, or None if there is no recipient."""
    if recipient is None:
        return None

    notification = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        link=link,
    )
    if email:
        send_notification_email(notification)
    return notification


def send_notification_email(notification) -> bool:
    """Best-effort email. Never raises -- a mail failure must not break a booking."""
    recipient = notification.recipient
    if not recipient.email:
        return False
    try:
        send_mail(
            subject="[%s] %s" % (settings.CLINIC_NAME, notification.title),
            message="%s\n\n-- \n%s\n%s"
            % (notification.message, settings.CLINIC_NAME, settings.CLINIC_PHONE),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Could not email notification %s", notification.pk)
        return False

    notification.emailed_at = timezone.now()
    notification.save(update_fields=["emailed_at"])
    return True


def _when(appointment):
    return timezone.localtime(appointment.scheduled_for).strftime("%d %b %Y at %I:%M %p")


# --- Appointment lifecycle -------------------------------------------------

def appointment_booked(appointment):
    link = reverse("appointments:detail", args=[appointment.pk])
    notify(
        appointment.patient.user,
        NotificationType.APPOINTMENT_BOOKED,
        "Appointment booked - %s" % appointment.reference,
        "Your appointment with %s is booked for %s. Reason: %s. "
        "We will confirm it shortly."
        % (appointment.dentist.display_name, _when(appointment), appointment.get_reason_display()),
        link=link,
    )
    notify(
        appointment.dentist.user,
        NotificationType.APPOINTMENT_BOOKED,
        "New appointment - %s" % _when(appointment),
        "%s booked a %s appointment with you."
        % (appointment.patient.user.display_name, appointment.get_reason_display()),
        link=link,
    )


def appointment_confirmed(appointment):
    notify(
        appointment.patient.user,
        NotificationType.APPOINTMENT_CONFIRMED,
        "Appointment confirmed - %s" % appointment.reference,
        "Your appointment with %s on %s is confirmed. Please arrive 10 minutes early."
        % (appointment.dentist.display_name, _when(appointment)),
        link=reverse("appointments:detail", args=[appointment.pk]),
    )


def appointment_cancelled(appointment, cancelled_by=None):
    detail = " Reason: %s." % appointment.cancellation_reason if appointment.cancellation_reason else ""
    link = reverse("appointments:detail", args=[appointment.pk])
    for user in (appointment.patient.user, appointment.dentist.user):
        if cancelled_by and user == cancelled_by:
            continue
        notify(
            user,
            NotificationType.APPOINTMENT_CANCELLED,
            "Appointment cancelled - %s" % appointment.reference,
            "The appointment on %s has been cancelled.%s" % (_when(appointment), detail),
            link=link,
        )


def appointment_rescheduled(appointment):
    link = reverse("appointments:detail", args=[appointment.pk])
    notify(
        appointment.patient.user,
        NotificationType.APPOINTMENT_BOOKED,
        "Appointment moved - %s" % appointment.reference,
        "Your appointment with %s is now on %s."
        % (appointment.dentist.display_name, _when(appointment)),
        link=link,
    )
    notify(
        appointment.dentist.user,
        NotificationType.APPOINTMENT_BOOKED,
        "Appointment moved - %s" % appointment.reference,
        "%s moved their appointment to %s."
        % (appointment.patient.user.display_name, _when(appointment)),
        link=link,
    )


def appointment_reminder(appointment, email=True):
    return notify(
        appointment.patient.user,
        NotificationType.APPOINTMENT_REMINDER,
        "Reminder: appointment on %s" % _when(appointment),
        "This is a reminder of your appointment with %s on %s at %s. "
        "To reschedule, open your appointment in the patient portal or call %s."
        % (
            appointment.dentist.display_name,
            _when(appointment),
            settings.CLINIC_ADDRESS,
            settings.CLINIC_PHONE,
        ),
        link=reverse("appointments:detail", args=[appointment.pk]),
        email=email,
    )


# --- Clinical and billing events -------------------------------------------

def treatment_recorded(treatment):
    notify(
        treatment.patient.user,
        NotificationType.TREATMENT_ADDED,
        "Treatment record added",
        "%s recorded a %s on %s. You can view the details in your treatment history."
        % (
            treatment.dentist.display_name,
            treatment.get_procedure_display(),
            treatment.treatment_date,
        ),
        link=reverse("records:treatment_detail", args=[treatment.pk]),
    )


def prescription_issued(prescription):
    notify(
        prescription.patient.user,
        NotificationType.PRESCRIPTION_ADDED,
        "New prescription issued",
        "%s issued a prescription on %s. Follow the dosage exactly as written."
        % (prescription.dentist.display_name, prescription.issued_on),
        link=reverse("records:prescription_detail", args=[prescription.pk]),
    )


def follow_up_reminder(treatment, email=True):
    return notify(
        treatment.patient.user,
        NotificationType.FOLLOW_UP,
        "Follow-up due on %s" % treatment.follow_up_date,
        "Your follow-up for the %s on %s is due on %s. %s"
        % (
            treatment.get_procedure_display(),
            treatment.treatment_date,
            treatment.follow_up_date,
            treatment.follow_up_instructions or "Please book an appointment.",
        ),
        link=reverse("appointments:book"),
        email=email,
    )


def bill_generated(bill):
    notify(
        bill.patient.user,
        NotificationType.BILL_GENERATED,
        "Invoice %s generated" % bill.invoice_number,
        "An invoice of %s has been generated. Balance due: %s."
        % (bill.total, bill.balance_due),
        link=reverse("billing:detail", args=[bill.pk]),
    )


def payment_received(payment):
    bill = payment.bill
    notify(
        bill.patient.user,
        NotificationType.PAYMENT_RECEIVED,
        "Payment received for %s" % bill.invoice_number,
        "We received %s by %s. Remaining balance: %s."
        % (payment.amount, payment.get_method_display(), bill.balance_due),
        link=reverse("billing:detail", args=[bill.pk]),
    )


def ai_urgency_alert(analysis):
    """Tell the clinic when the symptom checker flags something urgent."""
    from accounts.models import Role, User

    recipients = User.objects.filter(role=Role.ADMIN, is_active=True)
    link = reverse("aiassistant:symptom_detail", args=[analysis.pk])
    name = analysis.user.display_name
    for admin in recipients:
        notify(
            admin,
            NotificationType.AI_ALERT,
            "%s triage: %s" % (analysis.get_urgency_display().split(" -")[0], name),
            "%s used the symptom checker and the result was %s. Summary: %s"
            % (name, analysis.urgency, analysis.summary[:250]),
            link=link,
        )
