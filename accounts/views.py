from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordChangeDoneView, PasswordChangeView,
)
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy

from core.permissions import admin_required, staff_required

from .forms import (
    DentistProfileForm, LoginForm, PatientAdminNotesForm, PatientCreationForm,
    PatientProfileForm, PatientSignUpForm, StaffCreationForm, UserDetailsForm,
)
from .models import DentistProfile, PatientProfile, Role, User


class DentalLoginView(LoginView):
    template_name = "accounts/login.html"
    form_class = LoginForm
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse("core:dashboard")


class DentalLogoutView(LogoutView):
    next_page = reverse_lazy("core:home")


class DentalPasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field in form.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
        return form


class DentalPasswordChangeDoneView(PasswordChangeDoneView):
    template_name = "accounts/password_change_done.html"


def signup(request):
    """Public patient registration."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    if request.method == "POST":
        form = PatientSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request,
                "Welcome to the clinic, %s. Your patient record has been created."
                % user.first_name,
            )
            return redirect("core:dashboard")
    else:
        form = PatientSignUpForm()

    return render(request, "accounts/signup.html", {"form": form})


@login_required
def profile(request):
    """Self-service profile page; the form shown depends on the role."""
    user_form = UserDetailsForm(request.POST or None, instance=request.user)
    profile_form = None

    if request.user.is_patient:
        patient, _ = PatientProfile.objects.get_or_create(user=request.user)
        profile_form = PatientProfileForm(request.POST or None, instance=patient)
    elif request.user.is_dentist:
        dentist = getattr(request.user, "dentist_profile", None)
        if dentist:
            profile_form = DentistProfileForm(request.POST or None, instance=dentist)

    if request.method == "POST":
        forms_valid = user_form.is_valid() and (profile_form is None or profile_form.is_valid())
        if forms_valid:
            user_form.save()
            if profile_form:
                profile_form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile")

    return render(
        request,
        "accounts/profile.html",
        {"user_form": user_form, "profile_form": profile_form},
    )


# --- Patient directory (clinic staff) --------------------------------------

@staff_required
def patient_list(request):
    query = request.GET.get("q", "").strip()
    patients = (
        PatientProfile.objects.select_related("user")
        .annotate(
            appointment_count=Count("appointments", distinct=True),
            treatment_count=Count("treatments", distinct=True),
        )
        .order_by("user__first_name", "user__last_name", "pk")
    )
    if query:
        patients = patients.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__phone__icontains=query)
            | Q(user__email__icontains=query)
            | Q(patient_code__icontains=query)
        )

    page = Paginator(patients, 15).get_page(request.GET.get("page"))
    return render(
        request, "accounts/patient_list.html", {"page_obj": page, "query": query}
    )


@login_required
def patient_detail(request, pk):
    """Full clinical view of one patient. Patients may only open their own."""
    patient = get_object_or_404(
        PatientProfile.objects.select_related("user"), pk=pk
    )
    if request.user.is_patient and patient.user_id != request.user.id:
        raise PermissionDenied("You can only view your own record.")

    notes_form = None
    if request.user.is_admin_role or request.user.is_dentist:
        notes_form = PatientAdminNotesForm(
            request.POST or None, instance=patient, prefix="notes"
        )
        if request.method == "POST" and notes_form.is_valid():
            notes_form.save()
            messages.success(request, "Clinic notes saved.")
            return redirect("accounts:patient_detail", pk=patient.pk)

    context = {
        "patient": patient,
        "notes_form": notes_form,
        "appointments": patient.appointments.select_related("dentist__user")[:10],
        "treatments": patient.treatments.select_related("dentist__user")[:10],
        "prescriptions": patient.prescriptions.prefetch_related("items")[:5],
        "bills": patient.bills.prefetch_related("items", "payments")[:5],
        "history_entries": patient.history_entries.all()[:10],
        "symptom_analyses": patient.symptom_analyses.all()[:5],
        "care_plan": patient.care_plans.first(),
    }
    return render(request, "accounts/patient_detail.html", context)


@admin_required
def patient_create(request):
    if request.method == "POST":
        form = PatientCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(
                request, "Patient %s registered." % user.display_name
            )
            return redirect("accounts:patient_detail", pk=user.patient_profile.pk)
    else:
        form = PatientCreationForm()
    return render(
        request,
        "accounts/staff_form.html",
        {"form": form, "title": "Register a new patient", "submit_label": "Create patient"},
    )


# --- Dentist directory -----------------------------------------------------

def dentist_list(request):
    """Public-facing list of dentists, also used by staff."""
    dentists = DentistProfile.objects.select_related("user").filter(
        user__is_active=True
    )
    specialization = request.GET.get("specialization", "").strip()
    if specialization:
        dentists = dentists.filter(specialization__icontains=specialization)

    specializations = (
        DentistProfile.objects.values_list("specialization", flat=True).distinct()
    )
    return render(
        request,
        "accounts/dentist_list.html",
        {
            "dentists": dentists,
            "specializations": sorted(set(specializations)),
            "selected_specialization": specialization,
        },
    )


def dentist_detail(request, pk):
    dentist = get_object_or_404(
        DentistProfile.objects.select_related("user").prefetch_related("availabilities"),
        pk=pk,
    )
    return render(request, "accounts/dentist_detail.html", {"dentist": dentist})


@admin_required
def staff_list(request):
    staff = User.objects.filter(role__in=[Role.ADMIN, Role.DENTIST]).select_related(
        "dentist_profile"
    )
    return render(request, "accounts/staff_list.html", {"staff_members": staff})


@admin_required
def staff_create(request):
    if request.method == "POST":
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            if user.role == Role.DENTIST:
                messages.info(
                    request,
                    "Now complete the professional profile for %s." % user.display_name,
                )
                return redirect("accounts:dentist_profile_edit", user_id=user.pk)
            messages.success(request, "Administrator %s created." % user.display_name)
            return redirect("accounts:staff_list")
    else:
        form = StaffCreationForm()
    return render(
        request,
        "accounts/staff_form.html",
        {"form": form, "title": "Add a staff account", "submit_label": "Create account"},
    )


@admin_required
def dentist_profile_edit(request, user_id):
    """Create or edit the professional profile attached to a dentist account."""
    user = get_object_or_404(User, pk=user_id, role=Role.DENTIST)
    instance = getattr(user, "dentist_profile", None)

    if request.method == "POST":
        form = DentistProfileForm(request.POST, instance=instance)
        if form.is_valid():
            dentist = form.save(commit=False)
            dentist.user = user
            dentist.save()
            messages.success(request, "Dentist profile saved.")
            return redirect("accounts:dentist_detail", pk=dentist.pk)
    else:
        form = DentistProfileForm(instance=instance)

    return render(
        request,
        "accounts/staff_form.html",
        {
            "form": form,
            "title": "Professional profile - %s" % user.display_name,
            "submit_label": "Save profile",
        },
    )


@admin_required
def toggle_user_active(request, user_id):
    """Deactivate or reactivate an account without deleting its records."""
    if request.method != "POST":
        return redirect("accounts:staff_list")

    user = get_object_or_404(User, pk=user_id)
    if user == request.user:
        messages.error(request, "You cannot deactivate your own account.")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        messages.success(
            request,
            "%s has been %s."
            % (user.display_name, "reactivated" if user.is_active else "deactivated"),
        )
    return redirect(request.POST.get("next") or reverse("accounts:staff_list"))
