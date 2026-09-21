"""The Gemini API request/response handling, exercised with a mocked SDK client.

These tests check the exact shape of what we send to generate_content and how
we read the response, without making a network call or spending anything.
"""

import json
from types import SimpleNamespace
from unittest import mock

import pytest
from google.genai import errors as genai_errors

from aiassistant.services import gemini_provider as gemini
from aiassistant.services.gemini_provider import AIProviderError


def fake_response(text, *, finish_reason="STOP", block_reason=None,
                  model="gemini-3.6-flash", thoughts=0):
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=finish_reason)],
        prompt_feedback=SimpleNamespace(block_reason=block_reason),
        model_version=model,
        usage_metadata=SimpleNamespace(
            prompt_token_count=120,
            candidates_token_count=64,
            thoughts_token_count=thoughts,
        ),
    )


@pytest.fixture
def configured(settings):
    settings.GEMINI_API_KEY = "test-key"
    settings.AI_ENABLED = True
    settings.AI_MODEL = "gemini-3.6-flash"
    settings.AI_MAX_TOKENS = 2000
    settings.AI_EFFORT = "low"
    settings.AI_THINKING_BUDGET = ""
    gemini._client = None  # drop any cached client between tests
    yield settings
    gemini._client = None


@pytest.fixture
def client_mock(configured):
    client = mock.MagicMock()
    with mock.patch.object(gemini, "get_client", return_value=client):
        yield client


def sent(client_mock):
    """The kwargs of the single generate_content call."""
    return client_mock.models.generate_content.call_args.kwargs


def test_is_configured_requires_a_key(settings):
    settings.GEMINI_API_KEY = ""
    assert not gemini.is_configured()
    settings.GEMINI_API_KEY = "test-key"
    settings.AI_ENABLED = True
    assert gemini.is_configured()
    settings.AI_ENABLED = False
    assert not gemini.is_configured()


def test_chat_sends_the_expected_request(client_mock):
    client_mock.models.generate_content.return_value = fake_response(
        "Cold sensitivity is common."
    )

    result = gemini.chat(
        "Why are my teeth sensitive?",
        history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        context_block="Patient first name: Asha",
    )

    kwargs = sent(client_mock)
    config = kwargs["config"]
    assert kwargs["model"] == "gemini-3.6-flash"
    assert config.max_output_tokens == 2000

    # The frozen system instruction carries the safety rules.
    assert "never diagnose" in config.system_instruction
    assert "immediate care" in config.system_instruction

    # History is replayed with Gemini's role names, and the new turn carries
    # the patient context.
    assert [c.role for c in kwargs["contents"]] == ["user", "model", "user"]
    assert "Asha" in kwargs["contents"][-1].parts[0].text

    assert result.content == "Cold sensitivity is common."
    assert result.provider == "gemini"
    assert result.model == "gemini-3.6-flash"
    assert result.input_tokens == 120
    assert result.output_tokens == 64
    assert not result.is_fallback


def test_assistant_turns_are_relabelled_as_model(client_mock):
    """Gemini rejects the role name 'assistant'; ours must be translated."""
    client_mock.models.generate_content.return_value = fake_response("ok")

    gemini.chat("next", history=[{"role": "assistant", "content": "earlier answer"}])

    roles = [c.role for c in sent(client_mock)["contents"]]
    assert "assistant" not in roles
    assert roles == ["model", "user"]


def test_history_is_trimmed_to_the_configured_window(client_mock, settings):
    settings.AI_HISTORY_TURNS = 4
    client_mock.models.generate_content.return_value = fake_response("ok")

    history = [{"role": "user", "content": "q%s" % i} for i in range(20)]
    gemini.chat("latest question", history=history)

    assert len(sent(client_mock)["contents"]) == 5  # 4 replayed + the new turn


def test_thinking_budget_follows_effort(client_mock, settings):
    client_mock.models.generate_content.return_value = fake_response("ok")

    settings.AI_EFFORT = "low"
    gemini.chat("hello")
    assert sent(client_mock)["config"].thinking_config.thinking_budget == 0

    settings.AI_EFFORT = "high"
    gemini.chat("hello")
    assert sent(client_mock)["config"].thinking_config.thinking_budget == -1


def test_explicit_thinking_budget_overrides_effort(client_mock, settings):
    client_mock.models.generate_content.return_value = fake_response("ok")
    settings.AI_EFFORT = "low"
    settings.AI_THINKING_BUDGET = "512"

    gemini.chat("hello")

    assert sent(client_mock)["config"].thinking_config.thinking_budget == 512


def test_thinking_tokens_are_counted_as_output(client_mock):
    """They are billed as output, so the log must not undercount them."""
    client_mock.models.generate_content.return_value = fake_response("ok", thoughts=300)

    result = gemini.chat("hello")

    assert result.output_tokens == 364


def test_safety_filters_are_relaxed_for_dental_content(client_mock):
    """Bleeding and swelling are normal dental triage input, not self-harm."""
    client_mock.models.generate_content.return_value = fake_response("ok")

    gemini.chat("my gum is bleeding badly")

    thresholds = {
        str(s.category): str(s.threshold)
        for s in sent(client_mock)["config"].safety_settings
    }
    assert len(thresholds) == 4
    assert all("BLOCK_ONLY_HIGH" in t for t in thresholds.values())
    assert any("DANGEROUS_CONTENT" in c for c in thresholds)


def test_symptom_analysis_requests_structured_json(client_mock):
    payload = {
        "urgency": "URGENT", "summary": "Needs to be seen within a day.",
        "possible_areas": ["Dental infection"], "self_care_advice": ["Rinse with salt water."],
        "red_flags": ["Facial swelling"], "recommended_within": "Within 24 hours",
        "suggested_reason": "EMERGENCY",
    }
    client_mock.models.generate_content.return_value = fake_response(json.dumps(payload))

    result = gemini.analyze_symptoms({
        "symptom_labels": ["Tooth pain", "Swelling"], "pain_level": 8,
        "duration_label": "Started today", "has_swelling": True, "has_fever": True,
        "difficulty_swallowing": False, "description": "Cheek is swollen.",
    })

    config = sent(client_mock)["config"]
    assert config.response_mime_type == "application/json"
    schema = config.response_json_schema
    assert schema["required"] == [
        "urgency", "summary", "possible_areas", "self_care_advice",
        "red_flags", "recommended_within", "suggested_reason",
    ]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["urgency"]["enum"] == [
        "ROUTINE", "SOON", "URGENT", "EMERGENCY"
    ]

    # The submitted symptoms reach the prompt.
    prompt = sent(client_mock)["contents"][0].parts[0].text
    assert "Tooth pain, Swelling" in prompt
    assert "Pain level (0-10): 8" in prompt

    assert result.content["urgency"] == "URGENT"


def test_care_plan_requests_structured_json(client_mock):
    payload = {
        "headline": "Focus on flossing.", "daily_routine": ["Brush twice."],
        "diet_tips": ["Less sugar."], "warning_signs": ["Bleeding gums."],
        "next_checkup_advice": "Book in six months.",
    }
    client_mock.models.generate_content.return_value = fake_response(json.dumps(payload))

    result = gemini.build_care_plan("Patient first name: Asha\nSmoker: no")

    schema = sent(client_mock)["config"].response_json_schema
    assert schema["required"][0] == "headline"
    assert result.content["headline"] == "Focus on flossing."


def test_clinical_summary_is_capped_and_clinician_facing(client_mock):
    client_mock.models.generate_content.return_value = fake_response("- **Allergies:** none")

    result = gemini.clinical_summary("Patient first name: Asha")

    config = sent(client_mock)["config"]
    assert config.max_output_tokens == 800
    assert "qualified dentist" in config.system_instruction
    assert result.content.startswith("- **Allergies:**")


def test_a_blocked_prompt_is_a_provider_error(client_mock):
    client_mock.models.generate_content.return_value = fake_response(
        "", block_reason="SAFETY"
    )
    with pytest.raises(AIProviderError, match="blocked the prompt"):
        gemini.chat("something the filter rejects")


def test_a_blocked_answer_is_a_provider_error(client_mock):
    client_mock.models.generate_content.return_value = fake_response(
        "", finish_reason="SAFETY"
    )
    with pytest.raises(AIProviderError, match="unsafe"):
        gemini.chat("hello")


def test_a_truncated_answer_is_a_provider_error(client_mock):
    """Hitting the cap mid-JSON would otherwise surface as malformed output."""
    client_mock.models.generate_content.return_value = fake_response(
        '{"headline": "cut off', finish_reason="MAX_TOKENS"
    )
    with pytest.raises(AIProviderError, match="output token limit"):
        gemini.build_care_plan("context")


def test_empty_response_is_an_error(client_mock):
    client_mock.models.generate_content.return_value = fake_response("   ")
    with pytest.raises(AIProviderError, match="empty"):
        gemini.chat("hello")


def test_missing_text_is_an_error(client_mock):
    client_mock.models.generate_content.return_value = fake_response(None)
    with pytest.raises(AIProviderError, match="empty"):
        gemini.chat("hello")


def test_malformed_json_is_an_error(client_mock):
    client_mock.models.generate_content.return_value = fake_response("not json at all")
    with pytest.raises(AIProviderError, match="malformed JSON"):
        gemini.build_care_plan("context")


@pytest.mark.parametrize(
    "exc,expected",
    [
        (genai_errors.ClientError(400, {"error": {"message": "bad"}}), "Invalid request"),
        (genai_errors.ClientError(401, {"error": {"message": "bad key"}}), "invalid or lacks access"),
        (genai_errors.ClientError(403, {"error": {"message": "nope"}}), "invalid or lacks access"),
        (genai_errors.ClientError(404, {"error": {"message": "no model"}}), "not found"),
        (genai_errors.ClientError(429, {"error": {"message": "slow down"}}), "rate limit"),
        (genai_errors.ServerError(503, {"error": {"message": "busy"}}), "unavailable"),
    ],
)
def test_sdk_errors_become_provider_errors(client_mock, exc, expected):
    """Every SDK failure mode must be translated, so the caller can fall back."""
    client_mock.models.generate_content.side_effect = exc
    with pytest.raises(AIProviderError, match=expected):
        gemini.chat("hello")


def test_unexpected_exceptions_are_also_contained(client_mock):
    client_mock.models.generate_content.side_effect = ValueError("something odd")
    with pytest.raises(AIProviderError, match="Unexpected AI error"):
        gemini.chat("hello")
