"""Gemini API provider for the dental assistant.

Uses the official ``google-genai`` SDK. Every method raises ``AIProviderError``
on failure so the caller can fall back to the rule engine -- the application
must never break because the AI is unreachable.
"""

from __future__ import annotations

import json
import logging
import time

from django.conf import settings

logger = logging.getLogger(__name__)

PROVIDER_NAME = "gemini"


class AIProviderError(RuntimeError):
    """Raised for any failure that should trigger the offline fallback."""


try:  # The SDK is optional -- the app runs fully without it.
    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - exercised only in minimal installs
    genai = None
    genai_errors = None
    genai_types = None


# The system prompt is frozen so it stays a stable prefix that Gemini's
# implicit context caching can reuse across calls.
CHAT_SYSTEM_PROMPT = """You are the dental assistant for a dental clinic management system.

Your role:
- Answer general questions about teeth, gums, oral hygiene and dental procedures.
- Help patients make sense of symptoms in general terms.
- Explain how to use this system: booking, rescheduling and cancelling appointments,
  viewing treatment history, prescriptions and bills.

Hard rules:
- You are NOT a dentist and you never diagnose. Describe possibilities in general
  terms ("cold sensitivity has several common causes") and always point towards an
  examination by a qualified dentist.
- Never prescribe, name, or adjust the dose of any medicine. If asked, say the
  dentist decides that after examining the patient.
- If the person describes facial swelling, difficulty breathing or swallowing,
  uncontrolled bleeding, a knocked-out adult tooth, or a spreading infection, open
  your reply by telling them to seek immediate care, and say why.
- Stay strictly on dental and clinic topics. For anything else, say it is outside
  what you can help with and suggest their doctor.
- Never claim to know the contents of this patient's record beyond the context you
  are given, and never invent appointments, treatments, prices or results.

Style: warm, plain English, no jargon without explaining it. Two or three short
paragraphs at most, and use a short bullet list when steps are involved. Close
advice about a symptom with a brief reminder that only a dentist can diagnose it.
"""

SYMPTOM_SYSTEM_PROMPT = """You triage dental symptoms for a clinic's preliminary
symptom checker. You never diagnose; you categorize into possible areas of concern
and decide how soon a dentist should see the patient.

Urgency definitions -- choose exactly one:
- EMERGENCY: seek care immediately. Use for difficulty breathing or swallowing,
  swelling spreading to the eye, neck or floor of the mouth, uncontrolled bleeding,
  a knocked-out adult tooth, or swelling with fever.
- URGENT: within 24 hours. Facial or gum swelling, severe pain (8+/10), fever with
  dental symptoms, a loose adult tooth, or trauma to a tooth.
- SOON: within a few days. Moderate persistent pain, bleeding gums that do not
  settle, a broken filling, a symptom lasting weeks.
- ROUTINE: at the patient's convenience. Mild sensitivity, staining, mild bad
  breath, general check-up questions.

Always err towards the more cautious level when uncertain. Write summary in warm,
plain second-person English of 2-4 sentences, and end it with a sentence stating
this is not a diagnosis and a dentist must examine them.
"""

CARE_PLAN_SYSTEM_PROMPT = """You write short, practical, personalized preventive
dental-care plans for patients of a dental clinic, using only the profile data
supplied. Be specific and actionable rather than generic: if the patient does not
floss, say so and tell them how to start; if they smoke or have diabetes, connect
that directly to their gum risk. Never prescribe medicine and never diagnose.
Write in warm second-person English. Each list item is one sentence.
"""

CLINICAL_SUMMARY_SYSTEM_PROMPT = """You prepare a concise pre-visit briefing for a
qualified dentist from a patient's own record. The reader is a clinician, so be
factual and terse -- no patient-facing reassurance and no advice about what to do.
Surface in this order: medical alerts (allergies, conditions, medication, tobacco),
the presenting complaint, relevant treatment history, and any self-reported triage.
Do not suggest a diagnosis or a treatment plan; the dentist decides. Use short
markdown bullets, under 150 words. State plainly if information is missing.
"""

SYMPTOM_SCHEMA = {
    "type": "object",
    "properties": {
        "urgency": {"type": "string", "enum": ["ROUTINE", "SOON", "URGENT", "EMERGENCY"]},
        "summary": {"type": "string"},
        "possible_areas": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "self_care_advice": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
        },
        "red_flags": {"type": "array", "items": {"type": "string"}},
        "recommended_within": {"type": "string"},
        "suggested_reason": {
            "type": "string",
            "enum": [
                "CHECKUP", "PAIN", "CLEANING", "FILLING", "ROOT_CANAL",
                "EXTRACTION", "ORTHODONTIC", "COSMETIC", "FOLLOW_UP",
                "EMERGENCY", "OTHER",
            ],
        },
    },
    "required": [
        "urgency", "summary", "possible_areas", "self_care_advice",
        "red_flags", "recommended_within", "suggested_reason",
    ],
    "additionalProperties": False,
}

CARE_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "daily_routine": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "diet_tips": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "warning_signs": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
        "next_checkup_advice": {"type": "string"},
    },
    "required": [
        "headline", "daily_routine", "diet_tips", "warning_signs",
        "next_checkup_advice",
    ],
    "additionalProperties": False,
}

# Dental triage legitimately discusses bleeding, swelling and severe pain, which
# the default DANGEROUS_CONTENT filter can read as self-harm. Silently blocking a
# triage answer is worse than answering it, so only high-confidence hits block.
_SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
)

# Gemini 3 models think by default. 0 turns thinking off, -1 lets the model decide.
_EFFORT_THINKING_BUDGET = {
    "none": 0,
    "minimal": 0,
    "low": 0,
    "medium": -1,
    "high": -1,
    "max": -1,
}


def is_configured() -> bool:
    return bool(settings.AI_ENABLED and settings.GEMINI_API_KEY and genai is not None)


_client = None


def get_client():
    global _client
    if not is_configured():
        raise AIProviderError("Gemini API is not configured.")
    if _client is None:
        _client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=genai_types.HttpOptions(
                timeout=int(settings.AI_TIMEOUT_SECONDS * 1000),  # milliseconds
            ),
        )
    return _client


class Result:
    """Uniform return value from every provider call."""

    def __init__(self, content, *, provider=PROVIDER_NAME, model="", input_tokens=0,
                 output_tokens=0, latency_ms=0, is_fallback=False):
        self.content = content
        self.provider = provider
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.is_fallback = is_fallback


def _thinking_budget() -> int:
    override = getattr(settings, "AI_THINKING_BUDGET", "")
    if str(override).strip():
        try:
            return int(override)
        except (TypeError, ValueError):
            logger.warning("Ignoring non-numeric AI_THINKING_BUDGET=%r", override)
    return _EFFORT_THINKING_BUDGET.get(str(settings.AI_EFFORT).lower(), 0)


def _usage(response):
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return 0, 0
    # Thinking tokens are billed as output, so they belong in the output count.
    output = (getattr(usage, "candidates_token_count", 0) or 0) + (
        getattr(usage, "thoughts_token_count", 0) or 0
    )
    return getattr(usage, "prompt_token_count", 0) or 0, output


def _text_of(response) -> str:
    text = (response.text or "").strip()
    if not text:
        raise AIProviderError("Gemini returned an empty response.")
    return text


def _check_blocked(response):
    """Translate a filtered or truncated response into the fallback path."""
    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        raise AIProviderError("Gemini blocked the prompt (%s)." % feedback.block_reason)

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise AIProviderError("Gemini returned no candidates.")

    finish = str(getattr(candidates[0], "finish_reason", "") or "")
    if "SAFETY" in finish:
        raise AIProviderError("Gemini blocked the answer as unsafe.")
    if "RECITATION" in finish:
        raise AIProviderError("Gemini stopped the answer for recitation.")
    if "MAX_TOKENS" in finish:
        # Structured output would be truncated mid-JSON, so never use it.
        raise AIProviderError("Gemini hit the output token limit.")


def _contents(messages):
    """Map our user/assistant history onto Gemini's user/model roles."""
    out = []
    for turn in messages:
        role = "model" if turn["role"] == "assistant" else "user"
        out.append(
            genai_types.Content(
                role=role, parts=[genai_types.Part(text=turn["content"])]
            )
        )
    return out


def _call(*, system, messages, max_tokens=None, output_schema=None):
    """One generate_content call with uniform error translation."""
    client = get_client()
    started = time.monotonic()

    config_kwargs = {
        "system_instruction": system,
        "max_output_tokens": max_tokens or settings.AI_MAX_TOKENS,
        "thinking_config": genai_types.ThinkingConfig(
            thinking_budget=_thinking_budget()
        ),
        "safety_settings": [
            genai_types.SafetySetting(category=category, threshold="BLOCK_ONLY_HIGH")
            for category in _SAFETY_CATEGORIES
        ],
        # We never expose tools; disabling this also silences the SDK's AFC warning.
        "automatic_function_calling": genai_types.AutomaticFunctionCallingConfig(
            disable=True
        ),
    }
    if output_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_json_schema"] = output_schema

    try:
        response = client.models.generate_content(
            model=settings.AI_MODEL,
            contents=_contents(messages),
            config=genai_types.GenerateContentConfig(**config_kwargs),
        )
    except genai_errors.ClientError as exc:
        code = getattr(exc, "code", None)
        if code == 400:
            raise AIProviderError("Invalid request to Gemini: %s" % exc) from exc
        if code in (401, 403):
            raise AIProviderError("Gemini API key is invalid or lacks access.") from exc
        if code == 404:
            raise AIProviderError("Model %s not found." % settings.AI_MODEL) from exc
        if code == 429:
            raise AIProviderError("Gemini rate limit reached -- try again shortly.") from exc
        raise AIProviderError("Gemini API error (%s)." % code) from exc
    except genai_errors.ServerError as exc:
        raise AIProviderError(
            "Gemini is unavailable (%s)." % getattr(exc, "code", "5xx")
        ) from exc
    except genai_errors.APIError as exc:
        raise AIProviderError("Gemini API error: %s" % exc) from exc
    except Exception as exc:  # defensive: never let the request 500
        raise AIProviderError("Unexpected AI error: %s" % exc) from exc

    _check_blocked(response)

    latency_ms = int((time.monotonic() - started) * 1000)
    input_tokens, output_tokens = _usage(response)
    return response, Result(
        None,
        model=getattr(response, "model_version", "") or settings.AI_MODEL,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )


def chat(message: str, history=None, context_block: str = "") -> Result:
    """Conversational dental assistant turn."""
    messages = []
    for turn in (history or [])[-settings.AI_HISTORY_TURNS:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    user_content = message
    if context_block:
        # Volatile per-patient context goes after the stable system prefix.
        user_content = "%s\n\n---\nContext about this user (do not repeat verbatim):\n%s" % (
            message,
            context_block,
        )
    messages.append({"role": "user", "content": user_content})

    response, result = _call(system=CHAT_SYSTEM_PROMPT, messages=messages)
    result.content = _text_of(response)
    return result


def analyze_symptoms(payload: dict, context_block: str = "") -> Result:
    """Structured symptom triage."""
    lines = [
        "Symptoms selected: %s" % (", ".join(payload.get("symptom_labels") or []) or "none selected"),
        "Pain level (0-10): %s" % payload.get("pain_level", 0),
        "Duration: %s" % payload.get("duration_label", "unspecified"),
        "Facial or gum swelling: %s" % ("yes" if payload.get("has_swelling") else "no"),
        "Fever: %s" % ("yes" if payload.get("has_fever") else "no"),
        "Difficulty swallowing: %s" % ("yes" if payload.get("difficulty_swallowing") else "no"),
        "In their own words: %s" % (payload.get("description") or "(nothing added)"),
    ]
    if context_block:
        lines.append("")
        lines.append("Relevant patient record:")
        lines.append(context_block)

    response, result = _call(
        system=SYMPTOM_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "\n".join(lines)}],
        output_schema=SYMPTOM_SCHEMA,
    )
    result.content = _parse_json(_text_of(response))
    return result


def build_care_plan(profile_block: str) -> Result:
    response, result = _call(
        system=CARE_PLAN_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": "Write a preventive care plan for this patient:\n\n%s" % profile_block,
        }],
        output_schema=CARE_PLAN_SCHEMA,
    )
    result.content = _parse_json(_text_of(response))
    return result


def clinical_summary(context_block: str) -> Result:
    response, result = _call(
        system=CLINICAL_SUMMARY_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": "Prepare the pre-visit briefing:\n\n%s" % context_block,
        }],
        max_tokens=800,
    )
    result.content = _text_of(response)
    return result


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIProviderError("Gemini returned malformed JSON.") from exc
    if not isinstance(data, dict):
        raise AIProviderError("Gemini returned JSON that was not an object.")
    return data
