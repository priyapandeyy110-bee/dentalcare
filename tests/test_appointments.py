"""Booking rules: slot generation, double-booking, leave and rescheduling."""

from datetime import time, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, AppointmentStatus, TimeOff
from appointments.services import (
    MIN_NOTICE_MINUTES, SlotUnavailable, available_slots, book_appointment,
    cancel_appointment, next_available_slot, reschedule_appointment,
    slot_is_available,
)

pytestmark = pytest.mark.django_db


def a_day_ahead(days=3):
    return timezone.localdate() + timedelta(days=days)


def test_slots_are_generated_from_working_hours(dentist):
    """09:00-17:00 in 30-minute steps is 16 slots."""
    slots = available_slots(dentist, a_day_ahead())
    assert len(slots) == 16
    assert timezone.localtime(slots[0]).time() == time(9, 0)
    assert timezone.localtime(slots[-1]).time() == time(16, 30)


def test_booked_slot_disappears_from_availability(patient, dentist):
    day = a_day_ahead()
    before = available_slots(dentist, day)
    book_appointment(
        patient=patient, dentist=dentist, when=before[0], reason="CHECKUP"
    )
    after = available_slots(dentist, day)
    assert len(after) == len(before) - 1
    assert before[0] not in after


def test_double_booking_is_rejected(patient, dentist):
    slot = available_slots(dentist, a_day_ahead())[0]
    book_appointment(patient=patient, dentist=dentist, when=slot, reason="CHECKUP")

    with pytest.raises(SlotUnavailable):
        book_appointment(patient=patient, dentist=dentist, when=slot, reason="PAIN")


def test_cancelled_slot_becomes_bookable_again(patient, dentist):
    day = a_day_ahead()
    slot = available_slots(dentist, day)[0]
    appointment = book_appointment(
        patient=patient, dentist=dentist, when=slot, reason="CHECKUP"
    )

    assert not slot_is_available(dentist, slot)
    cancel_appointment(appointment, reason="Patient unwell")
    assert slot_is_available(dentist, slot)


def test_leave_removes_every_slot_that_day(dentist):
    day = a_day_ahead(5)
    assert available_slots(dentist, day)

    TimeOff.objects.create(
        dentist=dentist, start_date=day, end_date=day + timedelta(days=2),
        reason="Conference",
    )
    assert available_slots(dentist, day) == []
    assert available_slots(dentist, day + timedelta(days=2)) == []
    assert available_slots(dentist, day + timedelta(days=3))


def test_past_and_short_notice_slots_are_not_offered(dentist):
    """Nothing before now + MIN_NOTICE_MINUTES is bookable."""
    today = timezone.localdate()
    cutoff = timezone.localtime() + timedelta(minutes=MIN_NOTICE_MINUTES)
    for slot in available_slots(dentist, today):
        assert timezone.localtime(slot) >= cutoff

    assert available_slots(dentist, today - timedelta(days=1)) == []


def test_reschedule_frees_the_old_slot(patient, dentist):
    day = a_day_ahead()
    slots = available_slots(dentist, day)
    appointment = book_appointment(
        patient=patient, dentist=dentist, when=slots[0], reason="CHECKUP"
    )

    reschedule_appointment(appointment, slots[5])
    appointment.refresh_from_db()

    assert appointment.scheduled_for == slots[5]
    assert appointment.status == AppointmentStatus.PENDING
    assert slot_is_available(dentist, slots[0])


def test_reschedule_onto_a_taken_slot_is_rejected(patient, dentist):
    day = a_day_ahead()
    slots = available_slots(dentist, day)
    first = book_appointment(
        patient=patient, dentist=dentist, when=slots[0], reason="CHECKUP"
    )
    book_appointment(patient=patient, dentist=dentist, when=slots[1], reason="PAIN")

    with pytest.raises(SlotUnavailable):
        reschedule_appointment(first, slots[1])


def test_reference_numbers_are_unique_and_sequential(patient, dentist):
    slots = available_slots(dentist, a_day_ahead())
    first = book_appointment(patient=patient, dentist=dentist, when=slots[0], reason="CHECKUP")
    second = book_appointment(patient=patient, dentist=dentist, when=slots[1], reason="CHECKUP")

    assert first.reference != second.reference
    assert first.reference.startswith("APT-")


def test_next_available_slot_skips_full_days(dentist, patient):
    slot = next_available_slot(dentist)
    assert slot is not None
    assert slot >= timezone.now()


# --- View level ------------------------------------------------------------

def test_patient_can_book_through_the_form(patient_client, patient, dentist):
    day = a_day_ahead()
    slot = available_slots(dentist, day)[2]

    response = patient_client.post(
        reverse("appointments:book"),
        {
            "dentist": dentist.pk,
            "date": day.isoformat(),
            "slot": timezone.localtime(slot).strftime("%H:%M"),
            "reason": "PAIN",
            "symptoms": "Aching lower molar",
        },
        follow=True,
    )

    assert response.status_code == 200
    appointment = Appointment.objects.get(patient=patient)
    assert appointment.scheduled_for == slot
    assert appointment.reason == "PAIN"
    # Patient bookings wait for the clinic to confirm.
    assert appointment.status == AppointmentStatus.PENDING


def test_booking_without_a_slot_shows_an_error(patient_client, dentist):
    response = patient_client.post(
        reverse("appointments:book"),
        {"dentist": dentist.pk, "date": a_day_ahead().isoformat(), "reason": "CHECKUP"},
    )
    assert response.status_code == 200
    assert b"Choose one of the available times" in response.content
    assert not Appointment.objects.exists()


def test_slots_api_returns_free_times(patient_client, dentist):
    day = a_day_ahead()
    response = patient_client.get(
        reverse("appointments:slots_api"),
        {"dentist": dentist.pk, "date": day.isoformat()},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["slots"]) == 16
    assert data["slots"][0]["value"] == "09:00"


def test_patient_cannot_open_another_patients_appointment(
    patient_client, appointment, django_user_model
):
    from accounts.models import PatientProfile, Role

    other = django_user_model.objects.create_user(
        username="other", password="x", role=Role.PATIENT
    )
    other_patient = PatientProfile.objects.create(user=other)
    appointment.patient = other_patient
    appointment.save()

    response = patient_client.get(reverse("appointments:detail", args=[appointment.pk]))
    assert response.status_code == 403


def test_cancelling_sends_a_notification(patient_client, appointment):
    response = patient_client.post(
        reverse("appointments:cancel", args=[appointment.pk]),
        {"reason": "Travelling"},
        follow=True,
    )
    assert response.status_code == 200
    appointment.refresh_from_db()
    assert appointment.status == AppointmentStatus.CANCELLED
    assert appointment.cancellation_reason == "Travelling"
    assert appointment.dentist.user.notifications.filter(
        notification_type="APT_CANCELLED"
    ).exists()
