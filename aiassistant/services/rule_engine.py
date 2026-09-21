"""Deterministic dental assistant used when the Gemini API is unavailable.

This is a real, working engine -- not a stub. It answers FAQs by keyword
match, triages symptoms with an explicit scoring model, and builds care plans
from the patient profile. The whole AI feature set therefore works with no API
key, no network, and no cost, which matters for a demo or a viva.

When an API key *is* configured, the same functions still run as the fallback
path if the API call fails.
"""

from __future__ import annotations

import re

from . import knowledge as kb

PROVIDER_NAME = "rule-engine"

# Urgency scale used internally; mapped to UrgencyLevel at the boundary.
URGENCY_ORDER = ["ROUTINE", "SOON", "URGENT", "EMERGENCY"]


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())


def _tokens(text: str) -> set:
    return set(_normalize(text).split())


def _is_greeting(message: str) -> bool:
    cleaned = _normalize(message).strip()
    if not cleaned:
        return False
    if len(cleaned.split()) > 4:
        return False
    return any(cleaned.startswith(word) for word in kb.GREETING_WORDS)


def _is_appointment_query(message: str) -> bool:
    lowered = _normalize(message)
    return any(keyword in lowered for keyword in kb.APPOINTMENT_KEYWORDS)


DENTAL_VOCAB = {
    "tooth", "teeth", "gum", "gums", "dental", "dentist", "mouth", "jaw",
    "molar", "cavity", "cavities", "filling", "braces", "enamel", "plaque",
    "tartar", "crown", "denture", "implant", "floss", "brush", "breath",
    "ulcer", "swelling", "toothache", "root", "canal", "extraction", "wisdom",
    "bite", "chew", "saliva", "tongue", "oral", "whitening", "decay", "pain",
    "sensitive", "sensitivity", "bleeding", "appointment", "clinic", "bill",
    "prescription", "treatment", "checkup", "hygiene", "palate", "lip",
}


def _is_in_scope(message: str) -> bool:
    """Cheap topicality gate so the offline bot does not answer random questions."""
    return bool(_tokens(message) & DENTAL_VOCAB)


def match_faq(message: str):
    """Return the best-matching FAQ entry, or None."""
    lowered = _normalize(message)
    best = None
    best_score = 0
    for entry in kb.FAQ_ENTRIES:
        score = 0
        for keyword in entry["keywords"]:
            if keyword in lowered:
                # Longer keyword matches are more specific, so weight them.
                score += len(keyword.split()) * 2 + 1
        if score > best_score:
            best, best_score = entry, score
    return best if best_score > 0 else None


def answer_question(message: str, context: dict | None = None) -> str:
    """Answer a free-text dental question using the curated knowledge base."""
    context = context or {}

    if _is_greeting(message):
        name = context.get("user_first_name")
        greeting = kb.GREETING_RESPONSE
        if name:
            greeting = greeting.replace("Hello!", "Hello, %s!" % name, 1)
        return greeting

    red_flags = detect_red_flags(message)
    prefix = ""
    if red_flags:
        prefix = "**%s**\n\nWhat you mentioned (%s) needs urgent attention.\n\n" % (
            kb.EMERGENCY_NOTICE,
            ", ".join(sorted(set(red_flags))).lower(),
        )

    if _is_appointment_query(message):
        body = kb.APPOINTMENT_GUIDE
        upcoming = context.get("next_appointment")
        if upcoming:
            body = "Your next appointment is %s.\n\n%s" % (upcoming, body)
        return prefix + body

    entry = match_faq(message)
    if entry:
        return "%s**%s**\n\n%s\n\n_%s_" % (prefix, entry["title"], entry["answer"], kb.DISCLAIMER)

    if not _is_in_scope(message):
        return kb.OUT_OF_SCOPE_RESPONSE

    return prefix + kb.FALLBACK_RESPONSE + "\n\n_%s_" % kb.DISCLAIMER


def detect_red_flags(text: str) -> list:
    """Find emergency phrases in free text."""
    lowered = _normalize(text)
    found = []
    for phrase, label in kb.RED_FLAG_PHRASES.items():
        if _normalize(phrase) in lowered:
            found.append(label)
    return found


def _escalate(current: str, target: str) -> str:
    return target if URGENCY_ORDER.index(target) > URGENCY_ORDER.index(current) else current


REASON_BY_SYMPTOM = {
    "tooth_pain": "PAIN",
    "sensitivity": "CHECKUP",
    "gum_bleeding": "CLEANING",
    "swelling": "EMERGENCY",
    "bad_breath": "CLEANING",
    "discoloration": "COSMETIC",
    "loose_tooth": "CHECKUP",
    "jaw_pain": "CHECKUP",
    "broken_tooth": "EMERGENCY",
    "mouth_ulcer": "CHECKUP",
    "dry_mouth": "CHECKUP",
    "bleeding_after_extraction": "EMERGENCY",
}

RECOMMENDED_WITHIN = {
    "ROUTINE": "Within the next few weeks",
    "SOON": "Within 2 to 3 days",
    "URGENT": "Within 24 hours",
    "EMERGENCY": "Immediately",
}


def analyze_symptoms(payload: dict) -> dict:
    """Score a symptom submission into a structured preliminary assessment.

    ``payload`` keys: symptoms (list of codes), description, pain_level (0-10),
    duration, has_swelling, has_fever, difficulty_swallowing.
    """
    symptoms = [s for s in payload.get("symptoms") or [] if s in kb.SYMPTOM_RULES]
    description = payload.get("description") or ""
    pain = int(payload.get("pain_level") or 0)
    duration = payload.get("duration") or "days"

    urgency = "ROUTINE"
    areas: list = []
    advice: list = []

    for code in symptoms:
        rule = kb.SYMPTOM_RULES[code]
        urgency = _escalate(urgency, URGENCY_ORDER[min(rule["base_urgency"], 3)])
        for area in rule["areas"]:
            if area not in areas:
                areas.append(area)
        for tip in rule["advice"]:
            if tip not in advice:
                advice.append(tip)

    # Pain intensity escalates on its own.
    if pain >= 8:
        urgency = _escalate(urgency, "URGENT")
    elif pain >= 5:
        urgency = _escalate(urgency, "SOON")

    # Long-standing problems are rarely emergencies but should not be ignored.
    if duration in ("weeks", "months") and urgency == "ROUTINE":
        urgency = _escalate(urgency, "SOON")

    red_flags = detect_red_flags(description)

    if payload.get("difficulty_swallowing"):
        red_flags.append("Difficulty swallowing")
        urgency = "EMERGENCY"
    if payload.get("has_swelling") and payload.get("has_fever"):
        red_flags.append("Swelling together with fever")
        urgency = "EMERGENCY"
    elif payload.get("has_swelling"):
        red_flags.append("Facial or gum swelling")
        urgency = _escalate(urgency, "URGENT")
    elif payload.get("has_fever"):
        red_flags.append("Fever alongside dental symptoms")
        urgency = _escalate(urgency, "URGENT")

    if red_flags and urgency != "EMERGENCY":
        urgency = _escalate(urgency, "URGENT")

    # Free-text can reveal a symptom the checkboxes missed.
    if not symptoms and description:
        entry = match_faq(description)
        if entry:
            areas.append(entry["title"].rstrip("?"))
            advice.append("See the clinic guidance on: %s" % entry["title"])

    if not areas:
        areas = ["General dental examination needed to identify the cause"]
    if not advice:
        advice = [
            "Keep the area clean and rinse with warm salt water.",
            "Avoid very hot, very cold and sugary food until you are seen.",
        ]

    summary = _build_summary(symptoms, pain, duration, urgency, red_flags)
    suggested_reason = "CHECKUP"
    for code in symptoms:
        candidate = REASON_BY_SYMPTOM.get(code, "CHECKUP")
        if candidate == "EMERGENCY":
            suggested_reason = candidate
            break
        suggested_reason = candidate
    if urgency == "EMERGENCY":
        suggested_reason = "EMERGENCY"

    return {
        "urgency": urgency,
        "summary": summary,
        "possible_areas": areas[:6],
        "self_care_advice": advice[:6],
        "red_flags": sorted(set(red_flags)),
        "recommended_within": RECOMMENDED_WITHIN[urgency],
        "suggested_reason": suggested_reason,
        "provider": PROVIDER_NAME,
    }


DURATION_PHRASES = {
    "today": "starting today",
    "days": "over the last few days",
    "weeks": "for a few weeks",
    "months": "for several months",
}


def _build_summary(symptoms, pain, duration, urgency, red_flags) -> str:
    labels = [kb.SYMPTOM_RULES[c]["label"].lower() for c in symptoms]
    if labels:
        listed = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
        opening = "You reported %s %s" % (listed, DURATION_PHRASES.get(duration, ""))
    else:
        opening = "You described dental discomfort %s" % DURATION_PHRASES.get(duration, "")
    opening = opening.strip().rstrip(",") + "."

    if pain:
        opening += " You rated the pain %s out of 10." % pain

    if urgency == "EMERGENCY":
        closing = (
            " Based on what you described, this should be treated as a dental "
            "emergency. Contact the clinic or an emergency dental service now."
        )
    elif urgency == "URGENT":
        closing = (
            " This combination should be examined within about 24 hours rather "
            "than left to settle on its own."
        )
    elif urgency == "SOON":
        closing = (
            " This is not an emergency, but it is unlikely to resolve without "
            "treatment -- book a visit in the next few days."
        )
    else:
        closing = (
            " Nothing you described suggests an emergency. A routine check-up "
            "will identify the cause and prevent it getting worse."
        )

    if red_flags:
        closing += " Warning signs noted: %s." % ", ".join(sorted(set(red_flags))).lower()

    return opening + closing + " " + kb.DISCLAIMER


def build_care_plan(profile: dict) -> dict:
    """Build a personalized preventive-care plan from a patient profile dict.

    ``profile`` keys: is_smoker, brushes_twice_daily, flosses_daily,
    chronic_conditions, allergies, age, months_since_last_visit,
    recent_procedures (list of labels), open_symptoms (list of labels).
    """
    routine = list(kb.CARE_TIPS_BASE)
    diet = list(kb.DIET_TIPS_BASE)
    warnings = list(kb.WARNING_SIGNS_BASE)
    headline_bits = []

    if not profile.get("brushes_twice_daily", True):
        routine.insert(
            0,
            "Priority: you are not yet brushing twice a day. Add a second brush "
            "last thing at night -- that single change does more for your teeth "
            "than anything else on this list.",
        )
        headline_bits.append("build a twice-daily brushing habit")

    if not profile.get("flosses_daily", False):
        routine.insert(
            1,
            "Start cleaning between your teeth once a day. Begin with the back "
            "teeth where food packs most, and expect a little bleeding for the "
            "first week.",
        )
        headline_bits.append("start daily interdental cleaning")

    if profile.get("is_smoker"):
        routine.append(
            "Tobacco is driving gum inflammation and staining. Cutting down "
            "helps; stopping is the single biggest improvement you can make."
        )
        warnings.insert(
            0,
            "As a tobacco user, report any white or red patch, lump or "
            "non-healing ulcer immediately.",
        )
        headline_bits.append("reduce tobacco use")

    conditions = (profile.get("chronic_conditions") or "").lower()
    if "diabet" in conditions:
        routine.append(
            "With diabetes, gum disease progresses faster and heals slower. "
            "Aim for a dental check every 3 to 4 months and keep blood sugar "
            "well controlled -- the two affect each other."
        )
        headline_bits.append("protect your gums alongside diabetes care")
    if "heart" in conditions or "hypertension" in conditions or "blood pressure" in conditions:
        routine.append(
            "Bring an up-to-date list of your heart or blood-pressure "
            "medication to every visit; some affect bleeding, healing and "
            "cause dry mouth."
        )
    if "pregnan" in conditions:
        routine.append(
            "During pregnancy gums inflame more easily -- clean gently but "
            "thoroughly along the gum line and keep up routine check-ups."
        )

    if profile.get("allergies"):
        warnings.append(
            "Your recorded allergies (%s) are flagged on your chart -- confirm "
            "them at every visit before any medicine is prescribed."
            % profile["allergies"]
        )

    months = profile.get("months_since_last_visit")
    if months is None:
        next_checkup = "Book an initial check-up so we have a baseline record of your teeth and gums."
    elif months >= 12:
        next_checkup = (
            "It has been about %s months since your last visit. Book a check-up "
            "and a professional cleaning now." % months
        )
        headline_bits.append("catch up on an overdue check-up")
    elif months >= 6:
        next_checkup = "You are due for your six-monthly check-up -- book it this month."
    else:
        next_checkup = (
            "You are up to date. Your next routine check-up is due about %s "
            "months from now." % max(6 - months, 1)
        )

    age = profile.get("age")
    if age is not None and age >= 55:
        diet.append(
            "Root surfaces become exposed with age and decay easily -- a "
            "high-fluoride toothpaste is worth asking your dentist about."
        )
    if age is not None and age <= 16:
        diet.append("Avoid sticky sweets and fizzy drinks between meals.")

    for procedure in profile.get("recent_procedures") or []:
        lowered = procedure.lower()
        if "extraction" in lowered:
            routine.append(
                "After your recent extraction: rinse gently with warm salt "
                "water from day two, and avoid straws, smoking and vigorous "
                "spitting for the first few days."
            )
        elif "root canal" in lowered or "rct" in lowered:
            routine.append(
                "A root-treated tooth is more brittle -- avoid biting hard food "
                "on it until the final crown is fitted."
            )
        elif "orthodontic" in lowered or "braces" in lowered:
            routine.append(
                "With braces, clean around every bracket after meals and use "
                "interdental brushes; plaque left around brackets leaves "
                "permanent white marks."
            )
        elif "scaling" in lowered:
            routine.append(
                "Mild sensitivity for a few days after scaling is normal and "
                "settles; keep brushing gently along the gum line."
            )

    for symptom in profile.get("open_symptoms") or []:
        warnings.insert(0, "Recently reported and still unresolved: %s." % symptom)

    if headline_bits:
        headline = "Focus this month: " + "; ".join(headline_bits[:3]) + "."
    else:
        headline = "Your oral-care habits look solid -- keep them consistent."

    return {
        "headline": headline,
        "daily_routine": routine[:8],
        "diet_tips": diet[:6],
        "warning_signs": warnings[:6],
        "next_checkup_advice": next_checkup,
        "provider": PROVIDER_NAME,
    }


def summarize_for_dentist(context: dict) -> str:
    """Pre-visit briefing shown to the dentist (offline version)."""
    lines = []
    name = context.get("patient_name", "The patient")
    age = context.get("age")
    lines.append("**%s**%s" % (name, " - %s years" % age if age else ""))

    if context.get("allergies"):
        lines.append("- **Allergies:** %s" % context["allergies"])
    if context.get("chronic_conditions"):
        lines.append("- **Medical history:** %s" % context["chronic_conditions"])
    if context.get("current_medications"):
        lines.append("- **Current medication:** %s" % context["current_medications"])
    if context.get("is_smoker"):
        lines.append("- **Tobacco user** -- higher periodontal and healing risk.")

    complaint = context.get("chief_complaint")
    if complaint:
        lines.append("- **Reported today:** %s" % complaint)

    recent = context.get("recent_treatments") or []
    if recent:
        lines.append("- **Recent treatment:** %s" % "; ".join(recent[:4]))
    else:
        lines.append("- No previous treatment recorded at this clinic.")

    triage = context.get("latest_triage")
    if triage:
        lines.append("- **Self-reported triage:** %s" % triage)

    lines.append("")
    lines.append(
        "_Automatically compiled from the patient record. Verify clinically "
        "before treatment._"
    )
    return "\n".join(lines)
