from django.db import models
from django.urls import reverse
from django.utils import timezone

from accounts.models import DentistProfile, PatientProfile
from appointments.models import Appointment


class DentalHistoryEntry(models.Model):
    """Free-standing history item: past illness, surgery, habit or past treatment."""

    CATEGORY_CHOICES = [
        ("MEDICAL", "Medical condition"),
        ("DENTAL", "Past dental treatment"),
        ("ALLERGY", "Allergy"),
        ("SURGERY", "Surgery"),
        ("HABIT", "Habit"),
        ("OTHER", "Other"),
    ]

    patient = models.ForeignKey(
        PatientProfile, on_delete=models.CASCADE, related_name="history_entries"
    )
    category = models.CharField(max_length=10, choices=CATEGORY_CHOICES, default="DENTAL")
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    recorded_on = models.DateField(default=timezone.localdate)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="history_entries_recorded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_on", "-created_at"]
        verbose_name_plural = "Dental history entries"

    def __str__(self):
        return "%s - %s" % (self.patient.patient_code, self.title)


class ToothRegion(models.TextChoices):
    UPPER_RIGHT = "UR", "Upper right"
    UPPER_LEFT = "UL", "Upper left"
    LOWER_LEFT = "LL", "Lower left"
    LOWER_RIGHT = "LR", "Lower right"
    FULL_MOUTH = "FM", "Full mouth"
    NOT_APPLICABLE = "NA", "Not applicable"


class TreatmentStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class Treatment(models.Model):
    """Diagnosis + treatment recorded by a dentist for a visit (synopsis §5.4)."""

    PROCEDURE_CHOICES = [
        ("CONSULT", "Consultation"),
        ("SCALING", "Scaling and polishing"),
        ("FILLING", "Composite filling"),
        ("RCT", "Root canal treatment"),
        ("CROWN", "Crown / cap"),
        ("EXTRACTION", "Extraction"),
        ("IMPLANT", "Implant"),
        ("BRACES", "Orthodontic treatment"),
        ("WHITENING", "Teeth whitening"),
        ("GUM_TREATMENT", "Gum treatment"),
        ("DENTURE", "Denture"),
        ("XRAY", "X-ray / imaging"),
        ("OTHER", "Other"),
    ]

    patient = models.ForeignKey(
        PatientProfile, on_delete=models.CASCADE, related_name="treatments"
    )
    dentist = models.ForeignKey(
        DentistProfile, on_delete=models.PROTECT, related_name="treatments"
    )
    appointment = models.ForeignKey(
        Appointment, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="treatments",
    )
    treatment_date = models.DateField(default=timezone.localdate)
    chief_complaint = models.CharField(
        max_length=255, blank=True, help_text="In the patient's own words."
    )
    diagnosis = models.TextField()
    procedure = models.CharField(max_length=20, choices=PROCEDURE_CHOICES, default="CONSULT")
    tooth_region = models.CharField(
        max_length=2, choices=ToothRegion.choices, default=ToothRegion.NOT_APPLICABLE
    )
    tooth_numbers = models.CharField(
        max_length=60, blank=True, help_text="FDI notation, comma separated (e.g. 16, 17)."
    )
    treatment_notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=12, choices=TreatmentStatus.choices, default=TreatmentStatus.COMPLETED
    )
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_instructions = models.TextField(blank=True)
    follow_up_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-treatment_date", "-created_at"]
        indexes = [models.Index(fields=["treatment_date"])]

    def __str__(self):
        return "%s - %s (%s)" % (
            self.patient.patient_code,
            self.get_procedure_display(),
            self.treatment_date,
        )

    def get_absolute_url(self):
        return reverse("records:treatment_detail", args=[self.pk])

    @property
    def status_css(self):
        return {
            TreatmentStatus.PLANNED: "info",
            TreatmentStatus.IN_PROGRESS: "warning",
            TreatmentStatus.COMPLETED: "success",
            TreatmentStatus.CANCELLED: "secondary",
        }.get(self.status, "secondary")

    def can_be_viewed_by(self, user):
        if user.is_superuser or user.is_admin_role:
            return True
        if user.is_dentist:
            return True
        return self.patient.user_id == user.id


class Prescription(models.Model):
    """A prescription issued alongside a treatment."""

    patient = models.ForeignKey(
        PatientProfile, on_delete=models.CASCADE, related_name="prescriptions"
    )
    dentist = models.ForeignKey(
        DentistProfile, on_delete=models.PROTECT, related_name="prescriptions"
    )
    treatment = models.ForeignKey(
        Treatment, on_delete=models.CASCADE, null=True, blank=True,
        related_name="prescriptions",
    )
    issued_on = models.DateField(default=timezone.localdate)
    advice = models.TextField(blank=True, help_text="Diet, rinsing and aftercare advice.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_on", "-created_at"]

    def __str__(self):
        return "Prescription %s for %s" % (self.pk, self.patient.user.display_name)

    def get_absolute_url(self):
        return reverse("records:prescription_detail", args=[self.pk])

    def can_be_viewed_by(self, user):
        if user.is_superuser or user.is_admin_role or user.is_dentist:
            return True
        return self.patient.user_id == user.id


class PrescriptionItem(models.Model):
    """One drug line on a prescription."""

    prescription = models.ForeignKey(
        Prescription, on_delete=models.CASCADE, related_name="items"
    )
    medicine_name = models.CharField(max_length=120)
    dosage = models.CharField(max_length=80, help_text="e.g. 500 mg")
    frequency = models.CharField(max_length=80, help_text="e.g. Twice daily after meals")
    duration = models.CharField(max_length=60, help_text="e.g. 5 days")
    instructions = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return "%s %s" % (self.medicine_name, self.dosage)
