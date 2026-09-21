from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import redirect, render
from django.utils import timezone

from accounts.models import DentistProfile, PatientProfile
from aiassistant.models import AIQueryLog, SymptomAnalysis, UrgencyLevel
from aiassistant.services import assistant
from appointments.models import Appointment, AppointmentStatus
from billing.models import Bill, BillStatus, Payment
from records.models import Treatment

from .permissions import admin_required


def home(request):
    """Public landing page."""
    if request.user.is_authenticated:
        return redirect("core:dashboard")

    return render(
        request,
        "core/home.html",
        {
            "dentists": DentistProfile.objects.select_related("user").filter(
                is_accepting_patients=True, user__is_active=True
            )[:6],
            "ai_live": assistant.ai_is_live(),
        },
    )


@login_required
def dashboard(request):
    """Routes each role to its own dashboard."""
    if request.user.is_admin_role:
        return admin_dashboard(request)
    if request.user.is_dentist:
        return dentist_dashboard(request)
    return patient_dashboard(request)


def admin_dashboard(request):
    today = timezone.localdate()
    now = timezone.now()
    month_start = today.replace(day=1)

    appointments = Appointment.objects.all()
    bills = Bill.objects.exclude(status=BillStatus.CANCELLED)

    revenue_this_month = Payment.objects.filter(paid_on__gte=month_start).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")

    outstanding = Decimal("0")
    for bill in bills.filter(status__in=[BillStatus.UNPAID, BillStatus.PARTIAL]).prefetch_related(
        "items", "payments"
    ):
        outstanding += bill.balance_due

    stats = {
        "total_patients": PatientProfile.objects.count(),
        "total_dentists": DentistProfile.objects.count(),
        "appointments_today": appointments.filter(scheduled_for__date=today)
        .exclude(status=AppointmentStatus.CANCELLED)
        .count(),
        "appointments_pending": appointments.filter(
            status=AppointmentStatus.PENDING, scheduled_for__gte=now
        ).count(),
        "appointments_total": appointments.count(),
        "treatments_this_month": Treatment.objects.filter(
            treatment_date__gte=month_start
        ).count(),
        "revenue_this_month": revenue_this_month,
        "outstanding": outstanding,
        "urgent_triage": SymptomAnalysis.objects.filter(
            urgency__in=[UrgencyLevel.URGENT, UrgencyLevel.EMERGENCY],
            reviewed_by_dentist=False,
        ).count(),
        "ai_calls": AIQueryLog.objects.count(),
    }

    return render(
        request,
        "core/dashboard_admin.html",
        {
            "stats": stats,
            "todays_appointments": appointments.filter(scheduled_for__date=today)
            .exclude(status=AppointmentStatus.CANCELLED)
            .select_related("patient__user", "dentist__user")
            .order_by("scheduled_for")[:10],
            "pending_appointments": appointments.filter(
                status=AppointmentStatus.PENDING, scheduled_for__gte=now
            )
            .select_related("patient__user", "dentist__user")
            .order_by("scheduled_for")[:8],
            "urgent_analyses": SymptomAnalysis.objects.filter(
                urgency__in=[UrgencyLevel.URGENT, UrgencyLevel.EMERGENCY],
                reviewed_by_dentist=False,
            ).select_related("user")[:5],
            "recent_patients": PatientProfile.objects.select_related("user")[:5],
            "ai_live": assistant.ai_is_live(),
            "provider_label": assistant.provider_label(),
        },
    )


def dentist_dashboard(request):
    dentist = DentistProfile.objects.filter(user=request.user).first()
    if dentist is None:
        return render(
            request,
            "core/dashboard_dentist.html",
            {"dentist": None, "stats": {}, "todays_appointments": []},
        )

    today = timezone.localdate()
    now = timezone.now()
    appointments = Appointment.objects.filter(dentist=dentist)

    stats = {
        "today": appointments.filter(scheduled_for__date=today)
        .exclude(status=AppointmentStatus.CANCELLED)
        .count(),
        "upcoming": appointments.filter(
            scheduled_for__gte=now, status__in=["PENDING", "CONFIRMED"]
        ).count(),
        "patients_seen": Treatment.objects.filter(dentist=dentist)
        .values("patient")
        .distinct()
        .count(),
        "treatments": Treatment.objects.filter(dentist=dentist).count(),
        "pending_confirmation": appointments.filter(
            status=AppointmentStatus.PENDING, scheduled_for__gte=now
        ).count(),
    }

    follow_ups = (
        Treatment.objects.filter(
            dentist=dentist,
            follow_up_date__isnull=False,
            follow_up_date__lte=today + timedelta(days=14),
            follow_up_date__gte=today,
        )
        .select_related("patient__user")
        .order_by("follow_up_date")[:8]
    )

    return render(
        request,
        "core/dashboard_dentist.html",
        {
            "dentist": dentist,
            "stats": stats,
            "todays_appointments": appointments.filter(scheduled_for__date=today)
            .exclude(status=AppointmentStatus.CANCELLED)
            .select_related("patient__user")
            .order_by("scheduled_for"),
            "upcoming_appointments": appointments.filter(scheduled_for__gt=now)
            .exclude(status__in=["CANCELLED", "COMPLETED"])
            .select_related("patient__user")
            .order_by("scheduled_for")[:8],
            "follow_ups": follow_ups,
            "recent_treatments": Treatment.objects.filter(dentist=dentist)
            .select_related("patient__user")[:6],
        },
    )


def patient_dashboard(request):
    patient = PatientProfile.objects.filter(user=request.user).first()
    if patient is None:
        patient = PatientProfile.objects.create(user=request.user)

    now = timezone.now()
    appointments = patient.appointments.select_related("dentist__user")

    unpaid_total = Decimal("0")
    for bill in patient.bills.filter(
        status__in=[BillStatus.UNPAID, BillStatus.PARTIAL]
    ).prefetch_related("items", "payments"):
        unpaid_total += bill.balance_due

    next_appointment = (
        appointments.filter(scheduled_for__gte=now, status__in=["PENDING", "CONFIRMED"])
        .order_by("scheduled_for")
        .first()
    )

    return render(
        request,
        "core/dashboard_patient.html",
        {
            "patient": patient,
            "next_appointment": next_appointment,
            "upcoming_appointments": appointments.filter(
                scheduled_for__gte=now, status__in=["PENDING", "CONFIRMED"]
            ).order_by("scheduled_for")[:5],
            "past_appointments": appointments.filter(scheduled_for__lt=now)[:5],
            "treatments": patient.treatments.select_related("dentist__user")[:5],
            "prescriptions": patient.prescriptions.prefetch_related("items")[:3],
            "unpaid_total": unpaid_total,
            "care_plan": patient.care_plans.first(),
            "latest_analysis": patient.symptom_analyses.first(),
            "notifications": request.user.notifications.filter(is_read=False)[:5],
            "risk_flags": patient.risk_flags,
            "ai_live": assistant.ai_is_live(),
        },
    )


@admin_required
def reports(request):
    """Clinic reports (synopsis module 7)."""
    today = timezone.localdate()
    period = request.GET.get("period", "month")
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "year":
        start = today - timedelta(days=365)
    elif period == "all":
        start = None
    else:
        period = "month"
        start = today - timedelta(days=30)

    appointments = Appointment.objects.all()
    treatments = Treatment.objects.all()
    payments = Payment.objects.all()
    if start:
        appointments = appointments.filter(scheduled_for__date__gte=start)
        treatments = treatments.filter(treatment_date__gte=start)
        payments = payments.filter(paid_on__gte=start)

    status_breakdown = list(
        appointments.values("status").annotate(count=Count("id")).order_by("-count")
    )
    status_labels = dict(AppointmentStatus.choices)
    for row in status_breakdown:
        row["label"] = status_labels.get(row["status"], row["status"])

    procedure_breakdown = list(
        treatments.values("procedure")
        .annotate(count=Count("id"), revenue=Sum("cost"))
        .order_by("-count")
    )
    procedure_labels = dict(Treatment.PROCEDURE_CHOICES)
    for row in procedure_breakdown:
        row["label"] = procedure_labels.get(row["procedure"], row["procedure"])

    dentist_performance = list(
        DentistProfile.objects.annotate(
            appointment_count=Count(
                "appointments",
                filter=Q(appointments__scheduled_for__date__gte=start) if start else Q(),
                distinct=True,
            ),
            completed=Count(
                "appointments",
                filter=Q(appointments__status=AppointmentStatus.COMPLETED),
                distinct=True,
            ),
            treatment_count=Count("treatments", distinct=True),
        ).select_related("user")
    )

    revenue_by_month = list(
        payments.annotate(month=TruncMonth("paid_on"))
        .values("month")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    reason_breakdown = list(
        appointments.values("reason").annotate(count=Count("id")).order_by("-count")[:8]
    )
    reason_labels = dict(Appointment.REASON_CHOICES)
    for row in reason_breakdown:
        row["label"] = reason_labels.get(row["reason"], row["reason"])

    triage = SymptomAnalysis.objects.all()
    if start:
        triage = triage.filter(created_at__date__gte=start)
    triage_breakdown = list(
        triage.values("urgency").annotate(count=Count("id")).order_by("-count")
    )
    urgency_labels = dict(UrgencyLevel.choices)
    for row in triage_breakdown:
        row["label"] = urgency_labels.get(row["urgency"], row["urgency"])

    totals = {
        "appointments": appointments.count(),
        "completed": appointments.filter(status=AppointmentStatus.COMPLETED).count(),
        "cancelled": appointments.filter(status=AppointmentStatus.CANCELLED).count(),
        "no_show": appointments.filter(status=AppointmentStatus.NO_SHOW).count(),
        "treatments": treatments.count(),
        "revenue": payments.aggregate(total=Sum("amount"))["total"] or Decimal("0"),
        "new_patients": PatientProfile.objects.filter(
            created_at__date__gte=start
        ).count() if start else PatientProfile.objects.count(),
        "ai_calls": AIQueryLog.objects.filter(created_at__date__gte=start).count()
        if start
        else AIQueryLog.objects.count(),
    }
    completion_rate = (
        round(totals["completed"] * 100 / totals["appointments"])
        if totals["appointments"]
        else 0
    )

    return render(
        request,
        "core/reports.html",
        {
            "period": period,
            "start": start,
            "totals": totals,
            "completion_rate": completion_rate,
            "status_breakdown": status_breakdown,
            "procedure_breakdown": procedure_breakdown,
            "reason_breakdown": reason_breakdown,
            "triage_breakdown": triage_breakdown,
            "dentist_performance": dentist_performance,
            "revenue_by_month": revenue_by_month,
            "max_revenue": max(
                [row["total"] for row in revenue_by_month] or [Decimal("1")]
            ),
        },
    )


def handler403(request, exception=None):
    return render(request, "core/403.html", status=403)


def handler404(request, exception=None):
    return render(request, "core/404.html", status=404)


def handler500(request):
    return render(request, "core/500.html", status=500)
