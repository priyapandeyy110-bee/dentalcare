from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

phone_validator = RegexValidator(
    r"^[0-9+\-\s()]{7,20}$",
    "Enter a valid phone number (digits, spaces, +, -, brackets).",
)


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Administrator"
    DENTIST = "DENTIST", "Dentist"
    PATIENT = "PATIENT", "Patient"


class User(AbstractUser):
    """Single user table for all three roles (synopsis §10: Users -> Patients, Dentists)."""

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PATIENT)
    phone = models.CharField(max_length=20, blank=True, validators=[phone_validator])
    address = models.TextField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["first_name", "last_name", "username"]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_dentist(self):
        return self.role == Role.DENTIST

    @property
    def is_patient(self):
        return self.role == Role.PATIENT

    @property
    def initials(self):
        parts = [p for p in (self.first_name, self.last_name) if p]
        if not parts:
            return self.username[:2].upper()
        return "".join(p[0] for p in parts).upper()

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.localdate()
        born = self.date_of_birth
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class BloodGroup(models.TextChoices):
    A_POS = "A+", "A+"
    A_NEG = "A-", "A-"
    B_POS = "B+", "B+"
    B_NEG = "B-", "B-"
    AB_POS = "AB+", "AB+"
    AB_NEG = "AB-", "AB-"
    O_POS = "O+", "O+"
    O_NEG = "O-", "O-"
    UNKNOWN = "NA", "Not known"


class Gender(models.TextChoices):
    MALE = "M", "Male"
    FEMALE = "F", "Female"
    OTHER = "O", "Other"
    UNSPECIFIED = "U", "Prefer not to say"


class PatientProfile(models.Model):
    """Clinical + demographic details that belong only to patients."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    patient_code = models.CharField(max_length=16, unique=True, editable=False)
    gender = models.CharField(max_length=1, choices=Gender.choices, default=Gender.UNSPECIFIED)
    blood_group = models.CharField(
        max_length=3, choices=BloodGroup.choices, default=BloodGroup.UNKNOWN
    )
    emergency_contact_name = models.CharField(max_length=120, blank=True)
    emergency_contact_phone = models.CharField(
        max_length=20, blank=True, validators=[phone_validator]
    )
    allergies = models.TextField(blank=True, help_text="Known drug or material allergies.")
    chronic_conditions = models.TextField(
        blank=True, help_text="Diabetes, hypertension, heart conditions, etc."
    )
    current_medications = models.TextField(blank=True)
    is_smoker = models.BooleanField(default=False)
    brushes_twice_daily = models.BooleanField(default=True)
    flosses_daily = models.BooleanField(default=False)
    last_dental_visit = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self):
        return f"{self.patient_code} - {self.user.display_name}"

    def save(self, *args, **kwargs):
        if not self.patient_code:
            self.patient_code = self._generate_code()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        year = timezone.now().year
        prefix = f"PAT-{year}-"
        last = (
            PatientProfile.objects.filter(patient_code__startswith=prefix)
            .order_by("-patient_code")
            .first()
        )
        sequence = int(last.patient_code.rsplit("-", 1)[1]) + 1 if last else 1
        return f"{prefix}{sequence:04d}"

    def get_absolute_url(self):
        return reverse("accounts:patient_detail", args=[self.pk])

    @property
    def risk_flags(self):
        """Short list of clinically relevant flags shown across the UI."""
        flags = []
        if self.allergies.strip():
            flags.append("Allergies")
        if self.chronic_conditions.strip():
            flags.append("Chronic condition")
        if self.is_smoker:
            flags.append("Smoker")
        if not self.brushes_twice_daily:
            flags.append("Irregular brushing")
        return flags


class DentistProfile(models.Model):
    """Professional profile and scheduling defaults for a dentist."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="dentist_profile")
    registration_number = models.CharField(max_length=40, unique=True)
    specialization = models.CharField(
        max_length=120, default="General Dentistry",
        help_text="Orthodontics, Endodontics, Periodontics, Oral Surgery, ...",
    )
    qualification = models.CharField(max_length=120, default="BDS")
    experience_years = models.PositiveSmallIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(70)]
    )
    consultation_fee = models.DecimalField(max_digits=8, decimal_places=2, default=500)
    bio = models.TextField(blank=True)
    slot_duration_minutes = models.PositiveSmallIntegerField(
        default=30, validators=[MinValueValidator(10), MaxValueValidator(180)]
    )
    is_accepting_patients = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__first_name", "user__last_name"]

    def __str__(self):
        return f"Dr. {self.user.display_name} - {self.specialization}"

    @property
    def display_name(self):
        return f"Dr. {self.user.display_name}"

    def get_absolute_url(self):
        return reverse("accounts:dentist_detail", args=[self.pk])
