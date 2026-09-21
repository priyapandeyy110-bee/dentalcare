"""Slot generation and booking rules.

Kept out of the views so the same logic serves the booking form, the AJAX
slot lookup and the tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    ACTIVE_APPOINTMENT_STATUSES, Appointment, AppointmentStatus,
    DentistAvailability, TimeOff,
)

# How far ahead patients may book.
MAX_ADVANCE_DAYS = 60
# Minimum notice before a slot can be booked online.
MIN_NOTICE_MINUTES = 60


class SlotUnavailable(Exception):
    """Raised when the requested slot cannot be booked."""


def booking_window():
    today = timezone.localdate()
    return today, today + timedelta(days=MAX_ADVANCE_DAYS)


def is_on_leave(dentist, day) -> bool:
    return TimeOff.objects.filter(
        dentist=dentist, start_date__lte=day, end_date__gte=day
    ).exists()


def available_slots(dentist, day, *, exclude_appointment=None):
    """Return the bookable ``datetime`` slots for one dentist on one day.

    A slot is offered when it sits inside a working block, is not already
    taken by an active appointment, is not inside a leave period, and leaves
    at least ``MIN_NOTICE_MINUTES`` of notice.
    """
    if is_on_leave(dentist, day):
        return []

    blocks = DentistAvailability.objects.filter(
        dentist=dentist, weekday=day.weekday(), is_active=True
    )
    if not blocks:
        return []

    taken = set(
        Appointment.objects.filter(
            dentist=dentist,
            scheduled_for__date=day,
            status__in=ACTIVE_APPOINTMENT_STATUSES,
        )
        .exclude(pk=exclude_appointment.pk if exclude_appointment else None)
        .values_list("scheduled_for", flat=True)
    )
    taken_local = {timezone.localtime(value).replace(second=0, microsecond=0) for value in taken}

    earliest = timezone.localtime() + timedelta(minutes=MIN_NOTICE_MINUTES)
    slots = []
    current_tz = timezone.get_current_timezone()

    for block in blocks:
        for slot_time in block.slot_times(day):
            naive = datetime.combine(day, slot_time)
            aware = timezone.make_aware(naive, current_tz)
            local = timezone.localtime(aware).replace(second=0, microsecond=0)
            if local < earliest:
                continue
            if local in taken_local:
                continue
            slots.append(aware)

    return sorted(set(slots))


def slot_is_available(dentist, when, *, exclude_appointment=None) -> bool:
    local = timezone.localtime(when)
    return any(
        timezone.localtime(slot).replace(second=0, microsecond=0)
        == local.replace(second=0, microsecond=0)
        for slot in available_slots(
            dentist, local.date(), exclude_appointment=exclude_appointment
        )
    )


@transaction.atomic
def book_appointment(*, patient, dentist, when, reason, symptoms="", booked_by=None,
                     ai_triage_summary="", auto_confirm=False):
    """Create an appointment, re-checking availability inside the transaction."""
    if not slot_is_available(dentist, when):
        raise SlotUnavailable(
            "That slot has just been taken or is no longer available. "
            "Please choose another time."
        )

    appointment = Appointment(
        patient=patient,
        dentist=dentist,
        scheduled_for=when,
        duration_minutes=dentist.slot_duration_minutes,
        reason=reason,
        symptoms=symptoms,
        booked_by=booked_by,
        ai_triage_summary=ai_triage_summary,
        status=AppointmentStatus.CONFIRMED if auto_confirm else AppointmentStatus.PENDING,
    )
    try:
        appointment.save()
    except IntegrityError as exc:
        # The unique constraint is the last line of defence against a race.
        raise SlotUnavailable(
            "That slot was booked by someone else a moment ago. Please pick another."
        ) from exc
    return appointment


@transaction.atomic
def reschedule_appointment(appointment, when):
    if not slot_is_available(appointment.dentist, when, exclude_appointment=appointment):
        raise SlotUnavailable("That slot is not available. Please choose another time.")

    appointment.scheduled_for = when
    appointment.status = AppointmentStatus.PENDING
    appointment.reminder_sent_at = None
    try:
        appointment.save(
            update_fields=["scheduled_for", "status", "reminder_sent_at", "updated_at"]
        )
    except IntegrityError as exc:
        raise SlotUnavailable("That slot was just taken. Please pick another.") from exc
    return appointment


def cancel_appointment(appointment, *, reason="", cancelled_by=None):
    appointment.status = AppointmentStatus.CANCELLED
    appointment.cancellation_reason = reason[:255]
    if cancelled_by:
        appointment.notes = (
            "%s\nCancelled by %s on %s."
            % (
                appointment.notes,
                cancelled_by.display_name,
                timezone.localtime().strftime("%d %b %Y %H:%M"),
            )
        ).strip()
    appointment.save(
        update_fields=["status", "cancellation_reason", "notes", "updated_at"]
    )
    return appointment


def next_available_slot(dentist, *, days_ahead=14):
    """First free slot for a dentist within the next ``days_ahead`` days."""
    day = timezone.localdate()
    for _ in range(days_ahead):
        slots = available_slots(dentist, day)
        if slots:
            return slots[0]
        day += timedelta(days=1)
    return None


def day_schedule(dentist, day):
    """Working blocks plus booked appointments -- powers the dentist day view."""
    appointments = (
        Appointment.objects.filter(dentist=dentist, scheduled_for__date=day)
        .exclude(status=AppointmentStatus.CANCELLED)
        .select_related("patient__user")
        .order_by("scheduled_for")
    )
    return {
        "day": day,
        "on_leave": is_on_leave(dentist, day),
        "appointments": appointments,
        "free_slots": available_slots(dentist, day),
    }
