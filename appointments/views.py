from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from accounts.models import DentistProfile, PatientProfile
from core.permissions import staff_required
from notifications import services as notify

from .forms import (
    AppointmentStatusForm, AvailabilityForm, BookAppointmentForm,
    CancelAppointmentForm, RescheduleForm, StaffBookAppointmentForm, TimeOffForm,
)
from .models import (
    Appointment, AppointmentStatus, DentistAvailability, TimeOff,
)
from .services import SlotUnavailable, available_slots, book_appointment, cancel_appointment
from .services import day_schedule, reschedule_appointment


@login_required
def appointment_list(request):
    """Role-scoped appointment list with filters."""
    queryset = Appointment.objects.for_user(request.user).select_related(
        "patient__user", "dentist__user"
    )

    status = request.GET.get("status", "").strip()
    when = request.GET.get("when", "upcoming").strip()
    query = request.GET.get("q", "").strip()

    if status:
        queryset = queryset.filter(status=status)
    if when == "upcoming":
        queryset = queryset.filter(scheduled_for__gte=timezone.now()).order_by("scheduled_for")
    elif when == "past":
        queryset = queryset.filter(scheduled_for__lt=timezone.now())
    elif when == "today":
        queryset = queryset.filter(scheduled_for__date=timezone.localdate()).order_by(
            "scheduled_for"
        )
    if query:
        queryset = queryset.filter(_search_q(query))

    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "appointments/appointment_list.html",
        {
            "page_obj": page,
            "status_choices": AppointmentStatus.choices,
            "selected_status": status,
            "selected_when": when,
            "query": query,
        },
    )


def _search_q(query):
    return (
        Q(reference__icontains=query)
        | Q(patient__user__first_name__icontains=query)
        | Q(patient__user__last_name__icontains=query)
        | Q(patient__patient_code__icontains=query)
        | Q(dentist__user__first_name__icontains=query)
        | Q(dentist__user__last_name__icontains=query)
    )


@login_required
def appointment_detail(request, pk):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient__user", "dentist__user"), pk=pk
    )
    if not appointment.can_be_viewed_by(request.user):
        raise PermissionDenied("You cannot view this appointment.")

    status_form = None
    if request.user.is_admin_role or (
        request.user.is_dentist and appointment.dentist.user_id == request.user.id
    ):
        status_form = AppointmentStatusForm(request.POST or None, instance=appointment)
        if request.method == "POST" and status_form.is_valid():
            previous = Appointment.objects.get(pk=appointment.pk).status
            updated = status_form.save()
            if previous != updated.status:
                if updated.status == AppointmentStatus.CONFIRMED:
                    notify.appointment_confirmed(updated)
                elif updated.status == AppointmentStatus.CANCELLED:
                    notify.appointment_cancelled(updated, cancelled_by=request.user)
            messages.success(request, "Appointment updated.")
            return redirect("appointments:detail", pk=appointment.pk)

    return render(
        request,
        "appointments/appointment_detail.html",
        {
            "appointment": appointment,
            "status_form": status_form,
            "treatments": appointment.treatments.select_related("dentist__user"),
            "bills": appointment.bills.all(),
        },
    )


@login_required
def book(request):
    """Patients book for themselves; staff book on behalf of a patient."""
    is_staff_booking = request.user.is_admin_role or request.user.is_dentist
    form_class = StaffBookAppointmentForm if is_staff_booking else BookAppointmentForm

    patient = None
    if not is_staff_booking:
        patient = get_object_or_404(PatientProfile, user=request.user)

    initial = {}
    for key in ("dentist", "date", "reason"):
        if request.GET.get(key):
            initial[key] = request.GET[key]
    if request.GET.get("symptoms"):
        initial["symptoms"] = request.GET["symptoms"]

    form = form_class(request.POST or None, patient=patient, initial=initial)

    if request.method == "POST" and form.is_valid():
        target_patient = form.cleaned_data.get("patient") or patient
        try:
            appointment = book_appointment(
                patient=target_patient,
                dentist=form.cleaned_data["dentist"],
                when=form.cleaned_data["scheduled_for"],
                reason=form.cleaned_data["reason"],
                symptoms=form.cleaned_data.get("symptoms", ""),
                booked_by=request.user,
                ai_triage_summary=request.POST.get("ai_triage_summary", "")[:2000],
                auto_confirm=is_staff_booking,
            )
        except SlotUnavailable as exc:
            messages.error(request, str(exc))
        else:
            notify.appointment_booked(appointment)
            if is_staff_booking:
                notify.appointment_confirmed(appointment)
            messages.success(
                request,
                "Appointment %s booked for %s."
                % (
                    appointment.reference,
                    timezone.localtime(appointment.scheduled_for).strftime(
                        "%d %b %Y at %I:%M %p"
                    ),
                ),
            )
            return redirect("appointments:detail", pk=appointment.pk)

    return render(
        request,
        "appointments/book.html",
        {"form": form, "is_staff_booking": is_staff_booking},
    )


@login_required
def slots_api(request):
    """JSON slot lookup used by the booking page when dentist or date changes."""
    dentist_id = request.GET.get("dentist")
    day = parse_date(request.GET.get("date", ""))
    exclude_id = request.GET.get("exclude")

    if not dentist_id or not day:
        return JsonResponse({"slots": [], "message": "Choose a dentist and a date."})

    dentist = DentistProfile.objects.filter(pk=dentist_id).first()
    if dentist is None:
        return JsonResponse({"slots": [], "message": "Unknown dentist."}, status=404)

    exclude = Appointment.objects.filter(pk=exclude_id).first() if exclude_id else None
    slots = available_slots(dentist, day, exclude_appointment=exclude)

    return JsonResponse({
        "slots": [
            {
                "value": timezone.localtime(slot).strftime("%H:%M"),
                "label": timezone.localtime(slot).strftime("%I:%M %p"),
            }
            for slot in slots
        ],
        "message": "" if slots else "No free slots on that day. Try another date.",
    })


@login_required
def reschedule(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if not appointment.can_be_viewed_by(request.user):
        raise PermissionDenied("You cannot change this appointment.")
    if not appointment.is_editable:
        messages.error(request, "This appointment can no longer be changed.")
        return redirect("appointments:detail", pk=pk)

    form = RescheduleForm(request.POST or None, appointment=appointment)
    if request.method == "POST" and form.is_valid():
        try:
            reschedule_appointment(appointment, form.cleaned_data["scheduled_for"])
        except SlotUnavailable as exc:
            messages.error(request, str(exc))
        else:
            notify.appointment_rescheduled(appointment)
            messages.success(request, "Appointment moved.")
            return redirect("appointments:detail", pk=pk)

    return render(
        request,
        "appointments/reschedule.html",
        {"form": form, "appointment": appointment},
    )


@login_required
def cancel(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if not appointment.can_be_viewed_by(request.user):
        raise PermissionDenied("You cannot cancel this appointment.")
    if not appointment.is_editable:
        messages.error(request, "This appointment can no longer be cancelled.")
        return redirect("appointments:detail", pk=pk)

    form = CancelAppointmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        cancel_appointment(
            appointment,
            reason=form.cleaned_data.get("reason", ""),
            cancelled_by=request.user,
        )
        notify.appointment_cancelled(appointment, cancelled_by=request.user)
        messages.success(request, "Appointment %s cancelled." % appointment.reference)
        return redirect("appointments:list")

    return render(
        request,
        "appointments/cancel.html",
        {"form": form, "appointment": appointment},
    )


@staff_required
def schedule(request):
    """Day view of one dentist's diary."""
    if request.user.is_dentist:
        dentist = get_object_or_404(DentistProfile, user=request.user)
    else:
        dentist_id = request.GET.get("dentist")
        dentist = (
            DentistProfile.objects.filter(pk=dentist_id).first()
            or DentistProfile.objects.select_related("user").first()
        )
        if dentist is None:
            messages.warning(request, "No dentists have been added yet.")
            return redirect("core:dashboard")

    day = parse_date(request.GET.get("date", "")) or timezone.localdate()
    data = day_schedule(dentist, day)

    return render(
        request,
        "appointments/schedule.html",
        {
            "dentist": dentist,
            "all_dentists": DentistProfile.objects.select_related("user"),
            "schedule": data,
            "prev_day": day - timedelta(days=1),
            "next_day": day + timedelta(days=1),
            "today": timezone.localdate(),
        },
    )


@staff_required
def availability(request):
    """Manage weekly working hours and leave."""
    if request.user.is_dentist:
        dentist = get_object_or_404(DentistProfile, user=request.user)
    else:
        dentist_id = request.GET.get("dentist") or request.POST.get("dentist_id")
        dentist = (
            DentistProfile.objects.filter(pk=dentist_id).first()
            or DentistProfile.objects.select_related("user").first()
        )
        if dentist is None:
            messages.warning(request, "No dentists have been added yet.")
            return redirect("core:dashboard")

    availability_form = AvailabilityForm(prefix="slot")
    time_off_form = TimeOffForm(prefix="leave")

    if request.method == "POST":
        if "add_slot" in request.POST:
            availability_form = AvailabilityForm(request.POST, prefix="slot")
            if availability_form.is_valid():
                block = availability_form.save(commit=False)
                block.dentist = dentist
                exists = DentistAvailability.objects.filter(
                    dentist=dentist,
                    weekday=block.weekday,
                    start_time=block.start_time,
                ).exists()
                if exists:
                    messages.error(request, "That working block already exists.")
                else:
                    block.save()
                    messages.success(request, "Working hours added.")
                    return redirect("%s?dentist=%s" % (request.path, dentist.pk))
        elif "add_leave" in request.POST:
            time_off_form = TimeOffForm(request.POST, prefix="leave")
            if time_off_form.is_valid():
                leave = time_off_form.save(commit=False)
                leave.dentist = dentist
                leave.save()
                messages.success(request, "Leave recorded.")
                return redirect("%s?dentist=%s" % (request.path, dentist.pk))

    return render(
        request,
        "appointments/availability.html",
        {
            "dentist": dentist,
            "all_dentists": DentistProfile.objects.select_related("user"),
            "availability_form": availability_form,
            "time_off_form": time_off_form,
            "blocks": dentist.availabilities.all(),
            "leaves": dentist.time_off.filter(end_date__gte=timezone.localdate()),
        },
    )


@staff_required
def availability_delete(request, pk):
    block = get_object_or_404(DentistAvailability, pk=pk)
    if request.user.is_dentist and block.dentist.user_id != request.user.id:
        raise PermissionDenied("You can only edit your own working hours.")
    if request.method == "POST":
        dentist_id = block.dentist_id
        block.delete()
        messages.success(request, "Working block removed.")
        return redirect("%s?dentist=%s" % (reverse_availability(), dentist_id))
    return redirect("appointments:availability")


@staff_required
def time_off_delete(request, pk):
    leave = get_object_or_404(TimeOff, pk=pk)
    if request.user.is_dentist and leave.dentist.user_id != request.user.id:
        raise PermissionDenied("You can only edit your own leave.")
    if request.method == "POST":
        dentist_id = leave.dentist_id
        leave.delete()
        messages.success(request, "Leave removed.")
        return redirect("%s?dentist=%s" % (reverse_availability(), dentist_id))
    return redirect("appointments:availability")


def reverse_availability():
    return reverse("appointments:availability")
