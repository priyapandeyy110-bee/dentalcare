from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db import transaction

from .models import DentistProfile, PatientProfile, Role, User


class BootstrapMixin:
    """Apply Bootstrap classes without writing widgets out by hand."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)


class LoginForm(BootstrapMixin, AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "Username"})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"placeholder": "Password"})
    )


class PatientSignUpForm(BootstrapMixin, UserCreationForm):
    """Public self-registration -- always creates a PATIENT account."""

    first_name = forms.CharField(max_length=60)
    last_name = forms.CharField(max_length=60, required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20)
    date_of_birth = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    gender = forms.ChoiceField(
        choices=PatientProfile._meta.get_field("gender").choices, required=False
    )
    address = forms.CharField(widget=forms.Textarea, required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "date_of_birth")

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Role.PATIENT
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data["phone"]
        user.address = self.cleaned_data.get("address", "")
        user.date_of_birth = self.cleaned_data.get("date_of_birth")
        user.save()
        PatientProfile.objects.create(
            user=user, gender=self.cleaned_data.get("gender") or "U"
        )
        return user


class UserDetailsForm(BootstrapMixin, forms.ModelForm):
    """Shared personal-details form used on every profile page."""

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "date_of_birth", "address")
        widgets = {"date_of_birth": forms.DateInput(attrs={"type": "date"})}


class PatientProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = PatientProfile
        fields = (
            "gender", "blood_group", "emergency_contact_name", "emergency_contact_phone",
            "allergies", "chronic_conditions", "current_medications", "is_smoker",
            "brushes_twice_daily", "flosses_daily", "last_dental_visit",
        )
        widgets = {
            "last_dental_visit": forms.DateInput(attrs={"type": "date"}),
            "allergies": forms.Textarea(attrs={"rows": 2}),
            "chronic_conditions": forms.Textarea(attrs={"rows": 2}),
            "current_medications": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "is_smoker": "I use tobacco (smoked or chewed)",
            "brushes_twice_daily": "I brush twice a day",
            "flosses_daily": "I clean between my teeth daily",
        }


class PatientAdminNotesForm(BootstrapMixin, forms.ModelForm):
    """Clinic-only field, never shown to the patient."""

    class Meta:
        model = PatientProfile
        fields = ("notes",)
        widgets = {"notes": forms.Textarea(attrs={"rows": 4})}


class DentistProfileForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = DentistProfile
        fields = (
            "registration_number", "specialization", "qualification",
            "experience_years", "consultation_fee", "slot_duration_minutes",
            "is_accepting_patients", "bio",
        )
        widgets = {"bio": forms.Textarea(attrs={"rows": 3})}


class StaffCreationForm(BootstrapMixin, UserCreationForm):
    """Admin-side creation of dentist or administrator accounts."""

    first_name = forms.CharField(max_length=60)
    last_name = forms.CharField(max_length=60, required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, required=False)
    role = forms.ChoiceField(
        choices=[(Role.DENTIST, "Dentist"), (Role.ADMIN, "Administrator")]
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "role")

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.cleaned_data["role"]
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data.get("phone", "")
        if user.role == Role.ADMIN:
            user.is_staff = True
        user.save()
        return user


class PatientCreationForm(BootstrapMixin, UserCreationForm):
    """Front-desk registration of a walk-in patient."""

    first_name = forms.CharField(max_length=60)
    last_name = forms.CharField(max_length=60, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=20)
    date_of_birth = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone", "date_of_birth")

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Role.PATIENT
        user.email = self.cleaned_data.get("email", "")
        user.phone = self.cleaned_data["phone"]
        user.date_of_birth = self.cleaned_data.get("date_of_birth")
        user.save()
        PatientProfile.objects.create(user=user)
        return user
