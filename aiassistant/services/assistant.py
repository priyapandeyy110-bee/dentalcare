"""The single entry point every view uses for AI features.

Each function tries the Claude API first and silently falls back to the
rule engine if the API is unconfigured or fails, so the feature always
returns something usable. Every call is written to AIQueryLog.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from . import claude_provider as claude
from . import rule_engine
from .claude_provider import AIProviderError, Result

logger = logging.getLogger(__name__)


def ai_is_live() -> bool:
    """True when answers come from the Claude API rather than the rule engine."""
    return claude.is_configured()


def provider_label() -> str:
    return "Claude (%s)" % claude.settings.AI_MODEL if ai_is_live() else "Built-in dental engine"


def _log(user, feature, result, prompt_excerpt="", error=""):
    from aiassistant.models import AIQueryLog

    try:
        AIQueryLog.objects.create(
            user=user if (user and user.is_authenticated) else None,
            feature=feature,
            provider=result.provider if result else "none",
            model=result.model if result else "",
            prompt_excerpt=(prompt_excerpt or "")[:500],
            response_excerpt=(str(result.content) if result else "")[:500],
            input_tokens=result.input_tokens if result else 0,
            output_tokens=result.output_tokens if result else 0,
            latency_ms=result.latency_ms if result else 0,
            succeeded=bool(result) and not error,
            error_message=(error or "")[:300],
        )
    except Exception:  # logging must never break the request
        logger.exception("Failed to write AIQueryLog entry")


# --- Context builders ------------------------------------------------------

def build_patient_context(patient) -> str:
    """Compact, privacy-conscious record summary sent to the model."""
    if patient is None:
        return ""

    user = patient.user
    lines = ["Patient first name: %s" % (user.first_name or user.username)]
    if user.age:
        lines.append("Age: %s" % user.age)
    lines.append("Gender: %s" % patient.get_gender_display())
    if patient.allergies:
        lines.append("Allergies: %s" % patient.allergies)
    if patient.chronic_conditions:
        lines.append("Medical conditions: %s" % patient.chronic_conditions)
    if patient.current_medications:
        lines.append("Current medication: %s" % patient.current_medications)
    lines.append("Smoker: %s" % ("yes" if patient.is_smoker else "no"))
    lines.append("Brushes twice daily: %s" % ("yes" if patient.brushes_twice_daily else "no"))
    lines.append("Flosses daily: %s" % ("yes" if patient.flosses_daily else "no"))
    if patient.last_dental_visit:
        lines.append("Last dental visit: %s" % patient.last_dental_visit)

    recent = patient.treatments.select_related("dentist__user")[:3]
    if recent:
        lines.append("Recent treatment at this clinic:")
        for treatment in recent:
            lines.append(
                "  - %s on %s: %s"
                % (treatment.get_procedure_display(), treatment.treatment_date, treatment.diagnosis[:120])
            )

    upcoming = patient.appointments.upcoming().select_related("dentist__user").first()
    if upcoming:
        lines.append(
            "Next appointment: %s with %s (%s)"
            % (
                timezone.localtime(upcoming.scheduled_for).strftime("%d %b %Y at %H:%M"),
                upcoming.dentist.display_name,
                upcoming.get_reason_display(),
            )
        )
    else:
        lines.append("No upcoming appointment booked.")

    return "\n".join(lines)


def _profile_dict(patient) -> dict:
    """Rule-engine view of a patient profile."""
    months = None
    if patient.last_dental_visit:
        delta = timezone.localdate() - patient.last_dental_visit
        months = max(delta.days // 30, 0)

    open_symptoms = [
        analysis.summary[:100]
        for analysis in patient.symptom_analyses.filter(reviewed_by_dentist=False)[:2]
    ]

    return {
        "is_smoker": patient.is_smoker,
        "brushes_twice_daily": patient.brushes_twice_daily,
        "flosses_daily": patient.flosses_daily,
        "chronic_conditions": patient.chronic_conditions,
        "allergies": patient.allergies,
        "age": patient.user.age,
        "months_since_last_visit": months,
        "recent_procedures": [
            t.get_procedure_display() for t in patient.treatments.all()[:4]
        ],
        "open_symptoms": open_symptoms,
    }


# --- Public API ------------------------------------------------------------

def chat(user, message: str, history=None, patient=None) -> Result:
    """Answer a chat turn. Never raises."""
    context_block = build_patient_context(patient) if patient else ""

    if ai_is_live():
        try:
            result = claude.chat(message, history=history, context_block=context_block)
            _log(user, "chat", result, prompt_excerpt=message)
            return result
        except AIProviderError as exc:
            logger.warning("Claude chat failed, using rule engine: %s", exc)
            _log(user, "chat", None, prompt_excerpt=message, error=str(exc))

    rule_context = {
        "user_first_name": getattr(user, "first_name", "") or None,
    }
    if patient:
        upcoming = patient.appointments.upcoming().select_related("dentist__user").first()
        if upcoming:
            rule_context["next_appointment"] = "%s with %s" % (
                timezone.localtime(upcoming.scheduled_for).strftime("%d %b at %H:%M"),
                upcoming.dentist.display_name,
            )

    answer = rule_engine.answer_question(message, rule_context)
    result = Result(answer, provider=rule_engine.PROVIDER_NAME, is_fallback=True)
    _log(user, "chat", result, prompt_excerpt=message)
    return result


def analyze_symptoms(user, payload: dict, patient=None) -> Result:
    """Run the preliminary symptom checker. Never raises."""
    if ai_is_live():
        try:
            enriched = dict(payload)
            enriched["symptom_labels"] = _symptom_labels(payload.get("symptoms"))
            enriched["duration_label"] = _duration_label(payload.get("duration"))
            context_block = build_patient_context(patient) if patient else ""
            result = claude.analyze_symptoms(enriched, context_block=context_block)
            data = _validate_symptom_payload(result.content)
            data["provider"] = claude.PROVIDER_NAME
            result.content = data
            _log(user, "symptom", result, prompt_excerpt=str(payload.get("symptoms")))
            return result
        except AIProviderError as exc:
            logger.warning("Claude symptom analysis failed, using rule engine: %s", exc)
            _log(user, "symptom", None, error=str(exc))

    data = rule_engine.analyze_symptoms(payload)
    result = Result(data, provider=rule_engine.PROVIDER_NAME, is_fallback=True)
    _log(user, "symptom", result, prompt_excerpt=str(payload.get("symptoms")))
    return result


def build_care_plan(user, patient) -> Result:
    """Generate a personalized preventive-care plan. Never raises."""
    if ai_is_live():
        try:
            result = claude.build_care_plan(build_patient_context(patient))
            data = _validate_care_plan_payload(result.content)
            data["provider"] = claude.PROVIDER_NAME
            result.content = data
            _log(user, "care_plan", result, prompt_excerpt=patient.patient_code)
            return result
        except AIProviderError as exc:
            logger.warning("Claude care plan failed, using rule engine: %s", exc)
            _log(user, "care_plan", None, error=str(exc))

    data = rule_engine.build_care_plan(_profile_dict(patient))
    result = Result(data, provider=rule_engine.PROVIDER_NAME, is_fallback=True)
    _log(user, "care_plan", result, prompt_excerpt=patient.patient_code)
    return result


def clinical_summary(user, patient, appointment=None) -> Result:
    """Pre-visit briefing for the dentist. Never raises."""
    context_block = build_patient_context(patient)
    if appointment:
        context_block += "\nReason for this visit: %s\nPatient described: %s" % (
            appointment.get_reason_display(),
            appointment.symptoms or "(nothing added)",
        )

    if ai_is_live():
        try:
            result = claude.clinical_summary(context_block)
            _log(user, "clinical_summary", result, prompt_excerpt=patient.patient_code)
            return result
        except AIProviderError as exc:
            logger.warning("Claude clinical summary failed, using rule engine: %s", exc)
            _log(user, "clinical_summary", None, error=str(exc))

    latest = patient.symptom_analyses.first()
    text = rule_engine.summarize_for_dentist({
        "patient_name": patient.user.display_name,
        "age": patient.user.age,
        "allergies": patient.allergies,
        "chronic_conditions": patient.chronic_conditions,
        "current_medications": patient.current_medications,
        "is_smoker": patient.is_smoker,
        "chief_complaint": (appointment.symptoms if appointment else "") or (
            appointment.get_reason_display() if appointment else ""
        ),
        "recent_treatments": [
            "%s (%s)" % (t.get_procedure_display(), t.treatment_date)
            for t in patient.treatments.all()[:4]
        ],
        "latest_triage": latest.summary[:200] if latest else "",
    })
    result = Result(text, provider=rule_engine.PROVIDER_NAME, is_fallback=True)
    _log(user, "clinical_summary", result, prompt_excerpt=patient.patient_code)
    return result


# --- Validation ------------------------------------------------------------

VALID_URGENCY = {"ROUTINE", "SOON", "URGENT", "EMERGENCY"}
VALID_REASONS = {
    "CHECKUP", "PAIN", "CLEANING", "FILLING", "ROOT_CANAL", "EXTRACTION",
    "ORTHODONTIC", "COSMETIC", "FOLLOW_UP", "EMERGENCY", "OTHER",
}


def _string_list(value, limit=6):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:limit]


def _validate_symptom_payload(data: dict) -> dict:
    """Defensive validation -- structured outputs constrain the shape, we
    still bound the values before they reach the database and template."""
    urgency = str(data.get("urgency", "")).upper()
    if urgency not in VALID_URGENCY:
        raise AIProviderError("Unexpected urgency value from the model.")

    reason = str(data.get("suggested_reason", "")).upper()
    if reason not in VALID_REASONS:
        reason = "CHECKUP"

    summary = str(data.get("summary", "")).strip()
    if not summary:
        raise AIProviderError("Model returned an empty summary.")

    return {
        "urgency": urgency,
        "summary": summary[:4000],
        "possible_areas": _string_list(data.get("possible_areas")),
        "self_care_advice": _string_list(data.get("self_care_advice")),
        "red_flags": _string_list(data.get("red_flags"), limit=8),
        "recommended_within": str(data.get("recommended_within", ""))[:60],
        "suggested_reason": reason,
    }


def _validate_care_plan_payload(data: dict) -> dict:
    headline = str(data.get("headline", "")).strip()
    if not headline:
        raise AIProviderError("Model returned an empty care plan.")
    return {
        "headline": headline[:200],
        "daily_routine": _string_list(data.get("daily_routine"), limit=8),
        "diet_tips": _string_list(data.get("diet_tips")),
        "warning_signs": _string_list(data.get("warning_signs")),
        "next_checkup_advice": str(data.get("next_checkup_advice", ""))[:200],
    }


def _symptom_labels(codes):
    from aiassistant.models import SymptomAnalysis

    mapping = dict(SymptomAnalysis.SYMPTOM_CHOICES)
    return [mapping.get(code, code) for code in (codes or [])]


def _duration_label(code):
    from aiassistant.models import SymptomAnalysis

    return dict(SymptomAnalysis.DURATION_CHOICES).get(code, "unspecified")
