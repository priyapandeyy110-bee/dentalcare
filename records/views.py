from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import DentistProfile, PatientProfile
from aiassistant.services import assistant
from appointments.models import Appointment, AppointmentStatus
from core.permissions import staff_required
from notifications import services as notify

from .forms import (
    DentalHistoryForm, PrescriptionForm, PrescriptionItemFormSet, TreatmentForm,
)
from .models import DentalHistoryEntry, Prescription, Treatment


@login_required
def treatment_list(request):
    queryset = Treatment.objects.select_related("patient__user", "dentist__user")
    if request.user.is_patient:
        queryset = queryset.filter(patient__user=request.user)
    elif request.user.is_dentist:
        dentist_only = request.GET.get("mine", "1") == "1"
        if dentist_only:
            queryset = queryset.filter(dentist__user=request.user)

    query = request.GET.get("q", "").strip()
    if query:
        queryset = queryset.filter(
            Q(diagnosis__icontains=query)
            | Q(patient__user__first_name__icontains=query)
            | Q(patient__user__last_name__icontains=query)
            | Q(patient__patient_code__icontains=query)
        )

    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "records/treatment_list.html",
        {"page_obj": page, "query": query},
    )


@login_required
def treatment_detail(request, pk):
    treatment = get_object_or_404(
        Treatment.objects.select_related("patient__user", "dentist__user"), pk=pk
    )
    if not treatment.can_be_viewed_by(request.user):
        raise PermissionDenied("You cannot view this treatment record.")

    return render(
        request,
        "records/treatment_detail.html",
        {
            "treatment": treatment,
            "prescriptions": treatment.prescriptions.prefetch_related("items"),
            "bills": treatment.bills.all(),
        },
    )


@staff_required
def treatment_create(request, patient_id):
    """Record a diagnosis and treatment for a patient."""
    patient = get_object_or_404(PatientProfile.objects.select_related("user"), pk=patient_id)
    dentist = _acting_dentist(request)
    if dentist is None:
        messages.error(
            request,
            "Recording a treatment needs a dentist profile. Ask an administrator "
            "to set one up, or sign in as a dentist.",
        )
        return redirect("accounts:patient_detail", pk=patient.pk)

    appointment = None
    appointment_id = request.GET.get("appointment")
    if appointment_id:
        appointment = Appointment.objects.filter(pk=appointment_id, patient=patient).first()

    initial = {}
    if appointment:
        initial["chief_complaint"] = appointment.symptoms[:255] or appointment.get_reason_display()

    form = TreatmentForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        treatment = form.save(commit=False)
        treatment.patient = patient
        treatment.dentist = dentist
        treatment.appointment = appointment
        treatment.save()

        if appointment and appointment.status != AppointmentStatus.COMPLETED:
            appointment.status = AppointmentStatus.COMPLETED
            appointment.save(update_fields=["status", "updated_at"])

        patient.last_dental_visit = treatment.treatment_date
        patient.save(update_fields=["last_dental_visit", "updated_at"])

        notify.treatment_recorded(treatment)
        messages.success(request, "Treatment record saved.")
        return redirect("records:treatment_detail", pk=treatment.pk)

    return render(
        request,
        "records/treatment_form.html",
        {
            "form": form,
            "patient": patient,
            "appointment": appointment,
            "title": "Record treatment for %s" % patient.user.display_name,
        },
    )


@staff_required
def treatment_edit(request, pk):
    treatment = get_object_or_404(Treatment, pk=pk)
    if request.user.is_dentist and treatment.dentist.user_id != request.user.id:
        raise PermissionDenied("You can only edit treatments you recorded.")

    form = TreatmentForm(request.POST or None, instance=treatment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Treatment record updated.")
        return redirect("records:treatment_detail", pk=treatment.pk)

    return render(
        request,
        "records/treatment_form.html",
        {
            "form": form,
            "patient": treatment.patient,
            "appointment": treatment.appointment,
            "title": "Edit treatment record",
        },
    )


# --- Prescriptions ---------------------------------------------------------

@login_required
def prescription_list(request):
    queryset = Prescription.objects.select_related(
        "patient__user", "dentist__user"
    ).prefetch_related("items")
    if request.user.is_patient:
        queryset = queryset.filter(patient__user=request.user)
    elif request.user.is_dentist:
        queryset = queryset.filter(dentist__user=request.user)

    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(request, "records/prescription_list.html", {"page_obj": page})


@login_required
def prescription_detail(request, pk):
    prescription = get_object_or_404(
        Prescription.objects.select_related(
            "patient__user", "dentist__user"
        ).prefetch_related("items"),
        pk=pk,
    )
    if not prescription.can_be_viewed_by(request.user):
        raise PermissionDenied("You cannot view this prescription.")
    return render(
        request, "records/prescription_detail.html", {"prescription": prescription}
    )


@staff_required
def prescription_create(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related("user"), pk=patient_id)
    dentist = _acting_dentist(request)
    if dentist is None:
        messages.error(request, "Only a dentist account can issue a prescription.")
        return redirect("accounts:patient_detail", pk=patient.pk)

    treatment = None
    treatment_id = request.GET.get("treatment")
    if treatment_id:
        treatment = Treatment.objects.filter(pk=treatment_id, patient=patient).first()

    form = PrescriptionForm(request.POST or None)
    formset = PrescriptionItemFormSet(request.POST or None)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            prescription = form.save(commit=False)
            prescription.patient = patient
            prescription.dentist = dentist
            prescription.treatment = treatment
            prescription.save()
            formset.instance = prescription
            formset.save()

        notify.prescription_issued(prescription)
        messages.success(request, "Prescription issued.")
        return redirect("records:prescription_detail", pk=prescription.pk)

    return render(
        request,
        "records/prescription_form.html",
        {
            "form": form,
            "formset": formset,
            "patient": patient,
            "treatment": treatment,
            "allergies": patient.allergies,
        },
    )


# --- Dental history --------------------------------------------------------

@staff_required
def history_create(request, patient_id):
    patient = get_object_or_404(PatientProfile.objects.select_related("user"), pk=patient_id)
    form = DentalHistoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.patient = patient
        entry.recorded_by = request.user
        entry.save()
        messages.success(request, "History entry added.")
        return redirect("accounts:patient_detail", pk=patient.pk)

    return render(
        request,
        "records/history_form.html",
        {"form": form, "patient": patient, "entries": patient.history_entries.all()[:15]},
    )


@staff_required
def history_delete(request, pk):
    entry = get_object_or_404(DentalHistoryEntry, pk=pk)
    patient_id = entry.patient_id
    if request.method == "POST":
        entry.delete()
        messages.success(request, "History entry removed.")
    return redirect("accounts:patient_detail", pk=patient_id)


# --- AI briefing -----------------------------------------------------------

@staff_required
def clinical_briefing(request, patient_id):
    """AI-compiled pre-visit briefing for the dentist (synopsis: decision support)."""
    patient = get_object_or_404(PatientProfile.objects.select_related("user"), pk=patient_id)
    appointment = None
    appointment_id = request.GET.get("appointment")
    if appointment_id:
        appointment = Appointment.objects.filter(pk=appointment_id, patient=patient).first()

    result = assistant.clinical_summary(request.user, patient, appointment=appointment)

    return render(
        request,
        "records/clinical_briefing.html",
        {
            "patient": patient,
            "appointment": appointment,
            "summary": result.content,
            "is_fallback": result.is_fallback,
            "provider": result.provider,
        },
    )


def _acting_dentist(request):
    """The dentist profile to attribute a record to."""
    if request.user.is_dentist:
        return DentistProfile.objects.filter(user=request.user).first()
    # An administrator can record on behalf of a named dentist.
    dentist_id = request.POST.get("dentist_id") or request.GET.get("dentist")
    if dentist_id:
        return DentistProfile.objects.filter(pk=dentist_id).first()
    return DentistProfile.objects.select_related("user").first()
