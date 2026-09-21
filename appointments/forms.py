from datetime import datetime, timedelta

from django import forms
from django.utils import timezone

from accounts.forms import BootstrapMixin
from accounts.models import DentistProfile, PatientProfile

from .models import Appointment, DentistAvailability, TimeOff
from .services import MAX_ADVANCE_DAYS, available_slots


class BookAppointmentForm(BootstrapMixin, forms.Form):
    """Two-step booking: choose dentist + date, then pick from real free slots."""

    dentist = forms.ModelChoiceField(
        queryset=DentistProfile.objects.none(),
        empty_label="Select a dentist",
    )
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    slot = forms.ChoiceField(choices=[], required=False)
    reason = forms.ChoiceField(choices=Appointment.REASON_CHOICES)
    symptoms = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}),
        required=False,
        label="What are you experiencing?",
        help_text="Optional, but it helps the dentist prepare for your visit.",
    )

    def __init__(self, *args, **kwargs):
        self.patient = kwargs.pop("patient", None)
        super().__init__(*args, **kwargs)
        self.fields["dentist"].queryset = DentistProfile.objects.select_related(
            "user"
        ).filter(is_accepting_patients=True, user__is_active=True)

        today = timezone.localdate()
        self.fields["date"].widget.attrs.update({
            "min": today.isoformat(),
            "max": (today + timedelta(days=MAX_ADVANCE_DAYS)).isoformat(),
        })

        # Populate the slot choices from the submitted dentist + date so the
        # field validates against genuinely available times.
        self.slot_options = []
        dentist_id = self.data.get("dentist") or self.initial.get("dentist")
        date_value = self.data.get("date") or self.initial.get("date")
        if dentist_id and date_value:
            dentist = DentistProfile.objects.filter(pk=dentist_id).first()
            day = _parse_date(date_value)
            if dentist and day:
                self.slot_options = available_slots(dentist, day)
                self.fields["slot"].choices = [
                    (
                        timezone.localtime(slot).strftime("%H:%M"),
                        timezone.localtime(slot).strftime("%I:%M %p"),
                    )
                    for slot in self.slot_options
                ]

    def clean_date(self):
        day = self.cleaned_data["date"]
        today = timezone.localdate()
        if day < today:
            raise forms.ValidationError("You cannot book a date in the past.")
        if (day - today).days > MAX_ADVANCE_DAYS:
            raise forms.ValidationError(
                "Appointments can be booked up to %s days ahead." % MAX_ADVANCE_DAYS
            )
        return day

    def clean(self):
        cleaned = super().clean()
        dentist = cleaned.get("dentist")
        day = cleaned.get("date")
        slot = cleaned.get("slot")

        if dentist and day and not slot:
            self.add_error("slot", "Choose one of the available times.")
            return cleaned

        if dentist and day and slot:
            try:
                slot_time = datetime.strptime(slot, "%H:%M").time()
            except ValueError:
                self.add_error("slot", "That time is not valid.")
                return cleaned
            naive = datetime.combine(day, slot_time)
            cleaned["scheduled_for"] = timezone.make_aware(
                naive, timezone.get_current_timezone()
            )
        return cleaned


class StaffBookAppointmentForm(BookAppointmentForm):
    """Front-desk booking -- adds patient selection."""

    patient = forms.ModelChoiceField(
        queryset=PatientProfile.objects.none(),
        empty_label="Select a patient",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = PatientProfile.objects.select_related("user")
        self.order_fields(["patient", "dentist", "date", "slot", "reason", "symptoms"])


class RescheduleForm(BootstrapMixin, forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    slot = forms.ChoiceField(choices=[], required=False)

    def __init__(self, *args, **kwargs):
        self.appointment = kwargs.pop("appointment")
        super().__init__(*args, **kwargs)

        today = timezone.localdate()
        self.fields["date"].widget.attrs.update({
            "min": today.isoformat(),
            "max": (today + timedelta(days=MAX_ADVANCE_DAYS)).isoformat(),
        })

        self.slot_options = []
        date_value = self.data.get("date") or self.initial.get("date")
        day = _parse_date(date_value) if date_value else None
        if day:
            self.slot_options = available_slots(
                self.appointment.dentist, day, exclude_appointment=self.appointment
            )
            self.fields["slot"].choices = [
                (
                    timezone.localtime(slot).strftime("%H:%M"),
                    timezone.localtime(slot).strftime("%I:%M %p"),
                )
                for slot in self.slot_options
            ]

    def clean(self):
        cleaned = super().clean()
        day = cleaned.get("date")
        slot = cleaned.get("slot")
        if day and not slot:
            self.add_error("slot", "Choose one of the available times.")
            return cleaned
        if day and slot:
            try:
                slot_time = datetime.strptime(slot, "%H:%M").time()
            except ValueError:
                self.add_error("slot", "That time is not valid.")
                return cleaned
            cleaned["scheduled_for"] = timezone.make_aware(
                datetime.combine(day, slot_time), timezone.get_current_timezone()
            )
        return cleaned


class CancelAppointmentForm(BootstrapMixin, forms.Form):
    reason = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        label="Reason for cancelling (optional)",
    )


class AppointmentStatusForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ("status", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class AvailabilityForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = DentistAvailability
        fields = ("weekday", "start_time", "end_time", "is_active")
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }


class TimeOffForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = TimeOff
        fields = ("start_date", "end_date", "reason")
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }


def _parse_date(value):
    if not value:
        return None
    if hasattr(value, "year"):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None
