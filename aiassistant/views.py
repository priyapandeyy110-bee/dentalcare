from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from accounts.models import PatientProfile
from core.permissions import admin_required, staff_required
from notifications import services as notify

from .forms import ChatMessageForm, SymptomCheckerForm
from .models import (
    AIMessage, AIQueryLog, CarePlan, Conversation, MessageRole, SymptomAnalysis,
    UrgencyLevel,
)
from .services import assistant
from .services.knowledge import DISCLAIMER, FAQ_ENTRIES


def _patient_of(user):
    return PatientProfile.objects.filter(user=user).first()


def _history_for(conversation, limit=None):
    limit = limit or settings.AI_HISTORY_TURNS
    turns = list(
        conversation.messages.values("role", "content").order_by("-created_at", "-id")[:limit]
    )
    turns.reverse()
    return turns


@login_required
def chat(request, conversation_id=None):
    """The conversational dental assistant (synopsis module 5)."""
    if conversation_id:
        conversation = get_object_or_404(
            Conversation, pk=conversation_id, user=request.user
        )
    else:
        conversation = (
            Conversation.objects.filter(user=request.user, is_archived=False).first()
        )
        if conversation is None:
            conversation = Conversation.objects.create(user=request.user)

    form = ChatMessageForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        _handle_turn(request, conversation, form.cleaned_data["message"])
        return redirect("aiassistant:chat_detail", conversation_id=conversation.pk)

    return render(
        request,
        "aiassistant/chat.html",
        {
            "conversation": conversation,
            "conversations": Conversation.objects.filter(
                user=request.user, is_archived=False
            )[:15],
            "chat_messages": conversation.messages.all(),
            "form": form,
            "ai_live": assistant.ai_is_live(),
            "provider_label": assistant.provider_label(),
            "suggested_questions": SUGGESTED_QUESTIONS,
            "disclaimer": DISCLAIMER,
        },
    )


SUGGESTED_QUESTIONS = [
    "Why are my teeth sensitive to cold?",
    "How often should I really floss?",
    "My gums bleed when I brush -- is that normal?",
    "How do I book an appointment?",
    "What happens during a root canal?",
    "How can I stop bad breath?",
]


def _handle_turn(request, conversation, message_text):
    """Persist the user turn, get an answer, persist the assistant turn."""
    AIMessage.objects.create(
        conversation=conversation, role=MessageRole.USER, content=message_text
    )

    if conversation.title == "New conversation":
        conversation.title = message_text[:60]
        conversation.save(update_fields=["title"])

    # _history_for already includes the turn just saved, so drop it.
    history = _history_for(conversation)[:-1]
    result = assistant.chat(
        request.user,
        message_text,
        history=history,
        patient=_patient_of(request.user),
    )

    reply = AIMessage.objects.create(
        conversation=conversation,
        role=MessageRole.ASSISTANT,
        content=result.content,
        provider=result.provider,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=result.latency_ms,
        is_fallback=result.is_fallback,
    )
    conversation.touch()
    return reply


@login_required
def chat_new(request):
    conversation = Conversation.objects.create(user=request.user)
    return redirect("aiassistant:chat_detail", conversation_id=conversation.pk)


@login_required
def chat_delete(request, conversation_id):
    conversation = get_object_or_404(Conversation, pk=conversation_id, user=request.user)
    if request.method == "POST":
        conversation.delete()
        messages.success(request, "Conversation deleted.")
    return redirect("aiassistant:chat")


# --- Symptom checker -------------------------------------------------------

@login_required
def symptom_checker(request):
    form = SymptomCheckerForm(request.POST or None)
    patient = _patient_of(request.user)

    if request.method == "POST" and form.is_valid():
        payload = form.to_payload()
        result = assistant.analyze_symptoms(request.user, payload, patient=patient)
        data = result.content

        analysis = SymptomAnalysis.objects.create(
            user=request.user,
            patient=patient,
            symptoms=payload["symptoms"],
            description=payload["description"],
            pain_level=payload["pain_level"],
            duration=payload["duration"],
            has_swelling=payload["has_swelling"],
            has_fever=payload["has_fever"],
            difficulty_swallowing=payload["difficulty_swallowing"],
            urgency=data["urgency"],
            summary=data["summary"],
            possible_areas=data["possible_areas"],
            self_care_advice=data["self_care_advice"],
            red_flags=data["red_flags"],
            recommended_within=data["recommended_within"],
            suggested_reason=data["suggested_reason"],
            provider=result.provider,
            is_fallback=result.is_fallback,
        )

        if analysis.needs_immediate_care:
            notify.ai_urgency_alert(analysis)

        return redirect("aiassistant:symptom_detail", pk=analysis.pk)

    return render(
        request,
        "aiassistant/symptom_checker.html",
        {
            "form": form,
            "ai_live": assistant.ai_is_live(),
            "provider_label": assistant.provider_label(),
            "disclaimer": DISCLAIMER,
            "recent": SymptomAnalysis.objects.filter(user=request.user)[:5],
        },
    )


@login_required
def symptom_detail(request, pk):
    analysis = get_object_or_404(
        SymptomAnalysis.objects.select_related("user", "patient__user"), pk=pk
    )
    if not _can_view_analysis(request.user, analysis):
        raise PermissionDenied("You cannot view this assessment.")

    booking_url = "%s?%s" % (
        reverse("appointments:book"),
        urlencode({
            "reason": analysis.suggested_reason or "CHECKUP",
            "symptoms": analysis.description[:200],
        }),
    )

    return render(
        request,
        "aiassistant/symptom_detail.html",
        {
            "analysis": analysis,
            "booking_url": booking_url,
            "disclaimer": DISCLAIMER,
            "emergency_number": settings.CLINIC_EMERGENCY_NUMBER,
        },
    )


@login_required
def symptom_history(request):
    queryset = SymptomAnalysis.objects.select_related("user", "patient__user")
    if request.user.is_patient:
        queryset = queryset.filter(user=request.user)
    elif request.user.is_dentist:
        queryset = queryset.filter(patient__appointments__dentist__user=request.user).distinct()

    urgency = request.GET.get("urgency", "").strip()
    if urgency:
        queryset = queryset.filter(urgency=urgency)

    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "aiassistant/symptom_history.html",
        {
            "page_obj": page,
            "urgency_choices": UrgencyLevel.choices,
            "selected_urgency": urgency,
        },
    )


@staff_required
def symptom_mark_reviewed(request, pk):
    analysis = get_object_or_404(SymptomAnalysis, pk=pk)
    if request.method == "POST":
        analysis.reviewed_by_dentist = True
        analysis.save(update_fields=["reviewed_by_dentist"])
        messages.success(request, "Marked as reviewed.")
    return redirect("aiassistant:symptom_detail", pk=pk)


def _can_view_analysis(user, analysis):
    if user.is_superuser or user.is_admin_role or user.is_dentist:
        return True
    return analysis.user_id == user.id


# --- Care plan -------------------------------------------------------------

@login_required
def care_plan(request, patient_id=None):
    """Personalized preventive-care suggestions (synopsis 6.3)."""
    if patient_id:
        patient = get_object_or_404(PatientProfile, pk=patient_id)
        if request.user.is_patient and patient.user_id != request.user.id:
            raise PermissionDenied("You can only view your own care plan.")
    else:
        patient = _patient_of(request.user)
        if patient is None:
            messages.info(
                request, "Care plans are generated for patient accounts."
            )
            return redirect("core:dashboard")

    plan = patient.care_plans.first()

    if request.method == "POST":
        result = assistant.build_care_plan(request.user, patient)
        data = result.content
        plan = CarePlan.objects.create(
            patient=patient,
            headline=data["headline"],
            daily_routine=data["daily_routine"],
            diet_tips=data["diet_tips"],
            warning_signs=data["warning_signs"],
            next_checkup_advice=data["next_checkup_advice"],
            provider=result.provider,
            is_fallback=result.is_fallback,
        )
        messages.success(request, "Your care plan has been refreshed.")
        if patient_id:
            return redirect("aiassistant:care_plan_for", patient_id=patient.pk)
        return redirect("aiassistant:care_plan")

    return render(
        request,
        "aiassistant/care_plan.html",
        {
            "patient": patient,
            "plan": plan,
            "history": patient.care_plans.all()[1:6],
            "ai_live": assistant.ai_is_live(),
            "provider_label": assistant.provider_label(),
            "disclaimer": DISCLAIMER,
        },
    )


# --- Knowledge base + monitoring -------------------------------------------

def faq(request):
    """Static dental FAQ -- available without logging in."""
    query = request.GET.get("q", "").strip().lower()
    entries = FAQ_ENTRIES
    if query:
        entries = [
            entry
            for entry in FAQ_ENTRIES
            if query in entry["title"].lower()
            or query in entry["answer"].lower()
            or any(query in keyword for keyword in entry["keywords"])
        ]
    return render(
        request,
        "aiassistant/faq.html",
        {"entries": entries, "query": request.GET.get("q", ""), "disclaimer": DISCLAIMER},
    )


@admin_required
def ai_logs(request):
    """Administrator view of AI usage -- cost, latency and failures."""
    queryset = AIQueryLog.objects.select_related("user")
    feature = request.GET.get("feature", "").strip()
    if feature:
        queryset = queryset.filter(feature=feature)
    if request.GET.get("failed") == "1":
        queryset = queryset.filter(succeeded=False)

    page = Paginator(queryset, 25).get_page(request.GET.get("page"))

    summary = AIQueryLog.objects.aggregate(
        calls=Count("id"),
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        avg_latency=Avg("latency_ms"),
    )
    failures = AIQueryLog.objects.filter(succeeded=False).count()

    return render(
        request,
        "aiassistant/ai_logs.html",
        {
            "page_obj": page,
            "summary": summary,
            "failures": failures,
            "feature_choices": AIQueryLog.FEATURE_CHOICES,
            "selected_feature": feature,
            "ai_live": assistant.ai_is_live(),
            "provider_label": assistant.provider_label(),
        },
    )
