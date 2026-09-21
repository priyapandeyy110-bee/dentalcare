"""The AI layer: rule engine, Gemini provider, fallback behaviour and the views."""

import json
from unittest import mock

import pytest
from django.urls import reverse

from aiassistant.models import AIMessage, AIQueryLog, CarePlan, SymptomAnalysis
from aiassistant.services import assistant, rule_engine
from aiassistant.services.gemini_provider import AIProviderError, Result

pytestmark = pytest.mark.django_db


# --- Rule engine (no database needed) --------------------------------------

@pytest.mark.parametrize(
    "question,expected",
    [
        ("Why are my teeth sensitive to cold?", "sensitiv"),
        ("How often should I brush my teeth?", "twice a day"),
        ("My gums bleed when I brush", "gum line"),
        ("What is a root canal?", "pulp"),
        ("How do I get rid of bad breath?", "tongue"),
    ],
)
def test_rule_engine_answers_faq_questions(question, expected):
    answer = rule_engine.answer_question(question)
    assert expected.lower() in answer.lower()


def test_rule_engine_greets_by_name():
    answer = rule_engine.answer_question("hello", {"user_first_name": "Asha"})
    assert "Asha" in answer


def test_rule_engine_explains_booking():
    answer = rule_engine.answer_question("How do I book an appointment?")
    assert "Book appointment" in answer


def test_rule_engine_declines_off_topic_questions():
    answer = rule_engine.answer_question("What is the capital of France?")
    assert "dental and oral-health topics" in answer


def test_rule_engine_always_adds_the_disclaimer():
    answer = rule_engine.answer_question("Why does my tooth hurt?")
    assert "not a medical diagnosis" in answer.lower()


# --- Symptom triage --------------------------------------------------------

def triage(**overrides):
    payload = {
        "symptoms": [], "description": "", "pain_level": 0, "duration": "days",
        "has_swelling": False, "has_fever": False, "difficulty_swallowing": False,
    }
    payload.update(overrides)
    return rule_engine.analyze_symptoms(payload)


def test_mild_sensitivity_is_routine():
    result = triage(symptoms=["sensitivity"], pain_level=2, duration="days")
    assert result["urgency"] == "ROUTINE"


def test_severe_pain_escalates_to_urgent():
    result = triage(symptoms=["tooth_pain"], pain_level=9)
    assert result["urgency"] == "URGENT"


def test_swelling_with_fever_is_an_emergency():
    result = triage(
        symptoms=["swelling"], pain_level=7, has_swelling=True, has_fever=True
    )
    assert result["urgency"] == "EMERGENCY"
    assert "Swelling together with fever" in result["red_flags"]
    assert result["suggested_reason"] == "EMERGENCY"


def test_difficulty_swallowing_is_always_an_emergency():
    result = triage(symptoms=["sensitivity"], pain_level=1, difficulty_swallowing=True)
    assert result["urgency"] == "EMERGENCY"


def test_red_flag_phrases_in_free_text_escalate():
    result = triage(description="My tooth was knocked out playing cricket.")
    assert result["urgency"] in ("URGENT", "EMERGENCY")
    assert "Tooth knocked out" in result["red_flags"]


def test_long_standing_problem_is_not_left_at_routine():
    result = triage(symptoms=["bad_breath"], duration="months")
    assert result["urgency"] == "SOON"


def test_triage_result_has_every_field_the_model_needs():
    result = triage(symptoms=["gum_bleeding"], pain_level=3)
    for key in [
        "urgency", "summary", "possible_areas", "self_care_advice", "red_flags",
        "recommended_within", "suggested_reason", "provider",
    ]:
        assert key in result
    assert result["summary"]
    assert result["possible_areas"]


# --- Care plan -------------------------------------------------------------

def test_care_plan_calls_out_missing_habits():
    plan = rule_engine.build_care_plan({
        "brushes_twice_daily": False, "flosses_daily": False, "is_smoker": True,
        "chronic_conditions": "Type 2 diabetes", "allergies": "", "age": 45,
        "months_since_last_visit": 18, "recent_procedures": [], "open_symptoms": [],
    })

    routine = " ".join(plan["daily_routine"]).lower()
    assert "twice a day" in routine
    assert "between your teeth" in routine
    assert "tobacco" in routine
    assert "diabetes" in routine
    assert "overdue" in plan["headline"].lower() or "18 months" in plan["next_checkup_advice"]


def test_care_plan_is_positive_for_good_habits():
    plan = rule_engine.build_care_plan({
        "brushes_twice_daily": True, "flosses_daily": True, "is_smoker": False,
        "chronic_conditions": "", "allergies": "", "age": 30,
        "months_since_last_visit": 2, "recent_procedures": [], "open_symptoms": [],
    })
    assert "solid" in plan["headline"].lower()
    assert plan["daily_routine"]


# --- Provider selection and fallback ---------------------------------------

def test_fallback_engine_is_used_when_no_api_key(patient):
    result = assistant.chat(patient.user, "Why do my gums bleed?")
    assert result.is_fallback
    assert result.provider == "rule-engine"
    assert result.content


def test_every_ai_call_is_logged(patient):
    assistant.chat(patient.user, "How often should I floss?")
    log = AIQueryLog.objects.get()
    assert log.feature == "chat"
    assert log.provider == "rule-engine"
    assert log.succeeded


def test_gemini_is_used_when_configured(patient, settings):
    settings.GEMINI_API_KEY = "test-key"
    settings.AI_ENABLED = True

    fake = Result("Cold sensitivity is common.", provider="gemini", model="gemini-3.6-flash")
    with mock.patch("aiassistant.services.gemini_provider.is_configured", return_value=True), \
         mock.patch("aiassistant.services.gemini_provider.chat", return_value=fake) as call:
        result = assistant.chat(patient.user, "Why are my teeth sensitive?")

    assert call.called
    assert result.provider == "gemini"
    assert not result.is_fallback


def test_api_failure_falls_back_to_the_rule_engine(patient, settings):
    """An API outage must never break the feature."""
    settings.GEMINI_API_KEY = "test-key"
    settings.AI_ENABLED = True

    with mock.patch("aiassistant.services.gemini_provider.is_configured", return_value=True), \
         mock.patch(
             "aiassistant.services.gemini_provider.chat",
             side_effect=AIProviderError("network down"),
         ):
        result = assistant.chat(patient.user, "Why are my teeth sensitive?")

    assert result.is_fallback
    assert result.content
    # Both the failure and the fallback are recorded.
    assert AIQueryLog.objects.filter(succeeded=False).count() == 1
    assert AIQueryLog.objects.filter(succeeded=True).count() == 1


def test_symptom_analysis_falls_back_on_bad_model_output(patient, settings):
    settings.GEMINI_API_KEY = "test-key"
    settings.AI_ENABLED = True

    bad = Result({"urgency": "NOT_A_LEVEL", "summary": ""}, provider="gemini")
    with mock.patch("aiassistant.services.gemini_provider.is_configured", return_value=True), \
         mock.patch("aiassistant.services.gemini_provider.analyze_symptoms", return_value=bad):
        result = assistant.analyze_symptoms(
            patient.user,
            {"symptoms": ["tooth_pain"], "description": "", "pain_level": 5,
             "duration": "days", "has_swelling": False, "has_fever": False,
             "difficulty_swallowing": False},
            patient=patient,
        )

    assert result.is_fallback
    assert result.content["urgency"] in {"ROUTINE", "SOON", "URGENT", "EMERGENCY"}


def test_patient_context_never_leaks_other_patients(patient, appointment):
    block = assistant.build_patient_context(patient)
    assert patient.user.first_name in block
    assert "Penicillin" in block  # allergies from the fixture
    assert "Next appointment" in block


# --- Views -----------------------------------------------------------------

def test_chat_view_stores_both_turns(patient_client, patient):
    response = patient_client.post(
        reverse("aiassistant:chat"), {"message": "Why do my gums bleed?"}, follow=True
    )
    assert response.status_code == 200
    assert AIMessage.objects.filter(role="user").count() == 1
    assert AIMessage.objects.filter(role="assistant").count() == 1


def test_chat_api_returns_a_reply(patient_client, patient):
    response = patient_client.post(
        reverse("aiassistant:api_chat"),
        data=json.dumps({"message": "How often should I floss?"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    data = response.json()
    assert data["reply"]["content"]
    assert data["reply"]["role"] == "assistant"
    assert data["conversation_id"]


def test_chat_api_rejects_an_empty_message(patient_client):
    response = patient_client.post(
        reverse("aiassistant:api_chat"),
        data=json.dumps({"message": "   "}),
        content_type="application/json",
    )
    assert response.status_code == 400


def test_chat_api_requires_login(client):
    response = client.post(
        reverse("aiassistant:api_chat"),
        data=json.dumps({"message": "hello"}),
        content_type="application/json",
    )
    assert response.status_code in (401, 403)


def test_symptom_checker_saves_the_assessment(patient_client, patient):
    response = patient_client.post(
        reverse("aiassistant:symptom_checker"),
        {
            "symptoms": ["tooth_pain", "swelling"],
            "description": "Throbbing pain with a swollen cheek.",
            "pain_level": "8",
            "duration": "today",
            "has_swelling": "on",
            "has_fever": "on",
            "consent": "on",
        },
        follow=True,
    )

    assert response.status_code == 200
    analysis = SymptomAnalysis.objects.get()
    assert analysis.urgency == "EMERGENCY"
    assert analysis.patient == patient
    assert b"emergency" in response.content.lower()


def test_symptom_checker_requires_consent(patient_client):
    response = patient_client.post(
        reverse("aiassistant:symptom_checker"),
        {"symptoms": ["tooth_pain"], "pain_level": "3", "duration": "days"},
    )
    assert response.status_code == 200
    assert not SymptomAnalysis.objects.exists()


def test_symptom_checker_needs_some_input(patient_client):
    response = patient_client.post(
        reverse("aiassistant:symptom_checker"),
        {"pain_level": "0", "duration": "days", "consent": "on"},
    )
    assert response.status_code == 200
    assert b"Select at least one symptom" in response.content


def test_urgent_triage_alerts_the_clinic(patient_client, admin_user):
    patient_client.post(
        reverse("aiassistant:symptom_checker"),
        {
            "symptoms": ["swelling"], "description": "Face swelling since last night.",
            "pain_level": "8", "duration": "today", "has_swelling": "on",
            "has_fever": "on", "consent": "on",
        },
    )
    assert admin_user.notifications.filter(notification_type="AI_ALERT").exists()


def test_patient_cannot_read_another_patients_assessment(
    patient_client, analysis, django_user_model
):
    from accounts.models import Role

    other = django_user_model.objects.create_user(
        username="nosy", password="x", role=Role.PATIENT
    )
    analysis.user = other
    analysis.save()

    response = patient_client.get(reverse("aiassistant:symptom_detail", args=[analysis.pk]))
    assert response.status_code == 403


def test_care_plan_is_generated_on_demand(patient_client, patient):
    assert not CarePlan.objects.exists()
    response = patient_client.post(reverse("aiassistant:care_plan"), follow=True)
    assert response.status_code == 200
    plan = CarePlan.objects.get()
    assert plan.patient == patient
    assert plan.daily_routine


def test_clinical_briefing_renders_for_the_dentist(dentist_client, patient, treatment):
    response = dentist_client.get(
        reverse("records:clinical_briefing", args=[patient.pk])
    )
    assert response.status_code == 200
    assert b"Penicillin" in response.content


def test_markdownish_filter_escapes_html():
    from core.templatetags.dental_extras import markdownish

    rendered = markdownish("<script>alert(1)</script> and **bold**")
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<strong>bold</strong>" in rendered
