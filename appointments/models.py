from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import DentistProfile, PatientProfile


class Weekday(models.IntegerChoices):
    MONDAY = 0, "Monday"
    TUESDAY = 1, "Tuesday"
    WEDNESDAY = 2, "Wednesday"
    THURSDAY = 3, "Thursday"
    FRIDAY = 4, "Friday"
    SATURDAY = 5, "Saturday"
    SUNDAY = 6, "Sunday"


class DentistAvailability(models.Model):
    """Recurring weekly working hours used to generate bookable slots."""

    dentist = models.ForeignKey(
        DentistProfile, on_delete=models.CASCADE, related_name="availabilities"
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        verbose_name_plural = "Dentist availabilities"
        constraints = [
            models.UniqueConstraint(
                fields=["dentist", "weekday", "start_time"],
                name="unique_dentist_weekday_start",
            )
        ]

    def __str__(self):
        return "%s - %s %s-%s" % (
            self.dentist.display_name,
            self.get_weekday_display(),
            self.start_time.strftime("%H:%M"),
            self.end_time.strftime("%H:%M"),
        )

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "End time must be after the start time."})

    def slot_times(self, on_date):
        """Yield every slot start time this block produces for on_date."""
        step = timedelta(minutes=self.dentist.slot_duration_minutes)
        cursor = datetime.combine(on_date, self.start_time)
        end = datetime.combine(on_date, self.end_time)
        while cursor + step <= end:
            yield cursor.time()
            cursor += step


class TimeOff(models.Model):
    """A one-off block (leave, conference, surgery) that removes availability."""

    dentist = models.ForeignKey(DentistProfile, on_delete=models.CASCADE, related_name="time_off")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name_plural = "Time off"

    def __str__(self):
        return "%s off %s to %s" % (self.dentist.display_name, self.start_date, self.end_date)

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "End date must not be before the start date."})

    def covers(self, day):
        return self.start_date <= day <= self.end_date


class AppointmentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending confirmation"
    CONFIRMED = "CONFIRMED", "Confirmed"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No show"


ACTIVE_APPOINTMENT_STATUSES = (AppointmentStatus.PENDING, AppointmentStatus.CONFIRMED)


class AppointmentQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status__in=ACTIVE_APPOINTMENT_STATUSES)

    def upcoming(self):
        return self.active().filter(scheduled_for__gte=timezone.now()).order_by("scheduled_for")

    def past(self):
        return self.filter(scheduled_for__lt=timezone.now()).order_by("-scheduled_for")

    def for_user(self, user):
        """Scope a queryset to what this user is allowed to see."""
        if user.is_superuser or user.is_admin_role:
            return self
        if user.is_dentist:
            return self.filter(dentist__user=user)
        return self.filter(patient__user=user)


class Appointment(models.Model):
    """A booked slot between one patient and one dentist (synopsis module 4)."""

    REASON_CHOICES = [
        ("CHECKUP", "Routine check-up"),
        ("PAIN", "Tooth pain"),
        ("CLEANING", "Scaling / cleaning"),
        ("FILLING", "Filling / cavity"),
        ("ROOT_CANAL", "Root canal"),
        ("EXTRACTION", "Extraction"),
        ("ORTHODONTIC", "Braces / aligners"),
        ("COSMETIC", "Cosmetic / whitening"),
        ("FOLLOW_UP", "Follow-up visit"),
        ("EMERGENCY", "Emergency"),
        ("OTHER", "Other"),
    ]

    reference = models.CharField(max_length=20, unique=True, editable=False)
    patient = models.ForeignKey(
        PatientProfile, on_delete=models.CASCADE, related_name="appointments"
    )
    dentist = models.ForeignKey(
        DentistProfile, on_delete=models.PROTECT, related_name="appointments"
    )
    scheduled_for = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=30)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES, default="CHECKUP")
    symptoms = models.TextField(blank=True, help_text="What the patient described when booking.")
    status = models.CharField(
        max_length=12, choices=AppointmentStatus.choices, default=AppointmentStatus.PENDING
    )
    notes = models.TextField(blank=True, help_text="Internal clinic notes.")
    cancellation_reason = models.CharField(max_length=255, blank=True)
    booked_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="appointments_booked",
    )
    ai_triage_summary = models.TextField(
        blank=True, help_text="Preliminary AI guidance captured at booking time."
    )
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AppointmentQuerySet.as_manager()

    class Meta:
        ordering = ["-scheduled_for"]
        indexes = [
            models.Index(fields=["scheduled_for"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dentist", "scheduled_for"],
                condition=models.Q(status__in=["PENDING", "CONFIRMED"]),
                name="unique_active_slot_per_dentist",
            )
        ]

    def __str__(self):
        return "%s - %s with %s" % (
            self.reference,
            self.patient.user.display_name,
            self.dentist.display_name,
        )

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._generate_reference()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        stamp = timezone.now().strftime("%Y%m%d")
        prefix = "APT-%s-" % stamp
        last = (
            Appointment.objects.filter(reference__startswith=prefix)
            .order_by("-reference")
            .first()
        )
        sequence = int(last.reference.rsplit("-", 1)[1]) + 1 if last else 1
        return "%s%03d" % (prefix, sequence)

    def get_absolute_url(self):
        return reverse("appointments:detail", args=[self.pk])

    @property
    def end_time(self):
        return self.scheduled_for + timedelta(minutes=self.duration_minutes)

    @property
    def is_upcoming(self):
        return self.scheduled_for >= timezone.now() and self.status in ACTIVE_APPOINTMENT_STATUSES

    @property
    def is_editable(self):
        """Can still be rescheduled or cancelled."""
        return self.status in ACTIVE_APPOINTMENT_STATUSES and self.scheduled_for > timezone.now()

    @property
    def status_css(self):
        return {
            AppointmentStatus.PENDING: "warning",
            AppointmentStatus.CONFIRMED: "primary",
            AppointmentStatus.COMPLETED: "success",
            AppointmentStatus.CANCELLED: "secondary",
            AppointmentStatus.NO_SHOW: "danger",
        }.get(self.status, "secondary")

    def can_be_viewed_by(self, user):
        if user.is_superuser or user.is_admin_role:
            return True
        if user.is_dentist:
            return self.dentist.user_id == user.id
        return self.patient.user_id == user.id
