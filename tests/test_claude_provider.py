"""The Claude API request/response handling, exercised with a mocked SDK client.

These tests check the exact shape of what we send to the Messages API and how
we read the response, without making a network call or spending anything.
"""

import json
from types import SimpleNamespace
from unittest import mock

import anthropic
import pytest

from aiassistant.services import claude_provider as claude
from aiassistant.services.claude_provider import AIProviderError


class FakeBlock(SimpleNamespace):
    pass


def fake_response(text, *, stop_reason="end_turn", model="claude-opus-5"):
    return SimpleNamespace(
        content=[FakeBlock(type="text", text=text)],
        stop_reason=stop_reason,
        stop_details=None,
        model=model,
        usage=SimpleNamespace(input_tokens=120, output_tokens=64),
    )


@pytest.fixture
def configured(settings):
    settings.ANTHROPIC_API_KEY = "sk-ant-test-key"
    settings.AI_ENABLED = True
    settings.AI_MODEL = "claude-opus-5"
    settings.AI_MAX_TOKENS = 2000
    settings.AI_EFFORT = "low"
    claude._client = None  # drop any cached client between tests
    yield settings
    claude._client = None


@pytest.fixture
def client_mock(configured):
    client = mock.MagicMock()
    with mock.patch.object(claude, "get_client", return_value=client):
        yield client


def test_is_configured_requires_a_key(settings):
    settings.ANTHROPIC_API_KEY = ""
    assert not claude.is_configured()
    settings.ANTHROPIC_API_KEY = "sk-ant-x"
    settings.AI_ENABLED = True
    assert claude.is_configured()
    settings.AI_ENABLED = False
    assert not claude.is_configured()


def test_chat_sends_the_expected_request(client_mock):
    client_mock.messages.create.return_value = fake_response("Cold sensitivity is common.")

    result = claude.chat(
        "Why are my teeth sensitive?",
        history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        context_block="Patient first name: Asha",
    )

    kwargs = client_mock.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-opus-5"
    assert kwargs["max_tokens"] == 2000
    assert kwargs["output_config"]["effort"] == "low"

    # The system prompt is a cacheable block, and carries the safety rules.
    system = kwargs["system"][0]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "never diagnose" in system["text"]
    assert "immediate care" in system["text"]

    # History is replayed, and the new turn carries the patient context.
    assert [m["role"] for m in kwargs["messages"]] == ["user", "assistant", "user"]
    assert "Asha" in kwargs["messages"][-1]["content"]

    assert result.content == "Cold sensitivity is common."
    assert result.provider == "claude"
    assert result.input_tokens == 120
    assert result.output_tokens == 64
    assert not result.is_fallback


def test_history_is_trimmed_to_the_configured_window(client_mock, settings):
    settings.AI_HISTORY_TURNS = 4
    client_mock.messages.create.return_value = fake_response("ok")

    history = [{"role": "user", "content": "q%s" % i} for i in range(20)]
    claude.chat("latest question", history=history)

    messages = client_mock.messages.create.call_args.kwargs["messages"]
    assert len(messages) == 5  # 4 replayed + the new turn


def test_symptom_analysis_requests_structured_json(client_mock):
    payload = {
        "urgency": "URGENT", "summary": "Needs to be seen within a day.",
        "possible_areas": ["Dental infection"], "self_care_advice": ["Rinse with salt water."],
        "red_flags": ["Facial swelling"], "recommended_within": "Within 24 hours",
        "suggested_reason": "EMERGENCY",
    }
    client_mock.messages.create.return_value = fake_response(json.dumps(payload))

    result = claude.analyze_symptoms({
        "symptom_labels": ["Tooth pain", "Swelling"], "pain_level": 8,
        "duration_label": "Started today", "has_swelling": True, "has_fever": True,
        "difficulty_swallowing": False, "description": "Cheek is swollen.",
    })

    kwargs = client_mock.messages.create.call_args.kwargs
    fmt = kwargs["output_config"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["schema"]["required"] == [
        "urgency", "summary", "possible_areas", "self_care_advice",
        "red_flags", "recommended_within", "suggested_reason",
    ]
    assert fmt["schema"]["additionalProperties"] is False
    assert fmt["schema"]["properties"]["urgency"]["enum"] == [
        "ROUTINE", "SOON", "URGENT", "EMERGENCY"
    ]

    # The submitted symptoms reach the prompt.
    prompt = kwargs["messages"][0]["content"]
    assert "Tooth pain, Swelling" in prompt
    assert "Pain level (0-10): 8" in prompt

    assert result.content["urgency"] == "URGENT"


def test_care_plan_requests_structured_json(client_mock):
    payload = {
        "headline": "Focus on flossing.", "daily_routine": ["Brush twice."],
        "diet_tips": ["Less sugar."], "warning_signs": ["Bleeding gums."],
        "next_checkup_advice": "Book in six months.",
    }
    client_mock.messages.create.return_value = fake_response(json.dumps(payload))

    result = claude.build_care_plan("Patient first name: Asha\nSmoker: no")

    fmt = client_mock.messages.create.call_args.kwargs["output_config"]["format"]
    assert fmt["schema"]["required"][0] == "headline"
    assert result.content["headline"] == "Focus on flossing."


def test_clinical_summary_is_capped_and_clinician_facing(client_mock):
    client_mock.messages.create.return_value = fake_response("- **Allergies:** none")

    result = claude.clinical_summary("Patient first name: Asha")

    kwargs = client_mock.messages.create.call_args.kwargs
    assert kwargs["max_tokens"] == 800
    assert "qualified dentist" in kwargs["system"][0]["text"]
    assert result.content.startswith("- **Allergies:**")


def test_refusal_is_turned_into_a_provider_error(client_mock):
    client_mock.messages.create.return_value = fake_response("", stop_reason="refusal")
    with pytest.raises(AIProviderError, match="declined"):
        claude.chat("something the model refuses")


def test_empty_response_is_an_error(client_mock):
    client_mock.messages.create.return_value = fake_response("   ")
    with pytest.raises(AIProviderError, match="empty"):
        claude.chat("hello")


def test_malformed_json_is_an_error(client_mock):
    client_mock.messages.create.return_value = fake_response("not json at all")
    with pytest.raises(AIProviderError, match="malformed JSON"):
        claude.build_care_plan("context")


def _api_error(cls, **kwargs):
    """Build an SDK exception without going through its real constructor."""
    exc = cls.__new__(cls)
    Exception.__init__(exc, "boom")
    for key, value in kwargs.items():
        setattr(exc, key, value)
    return exc


@pytest.mark.parametrize(
    "exc_class,kwargs,expected",
    [
        (anthropic.AuthenticationError, {"message": "bad key"}, "API key is invalid"),
        (anthropic.RateLimitError, {"message": "slow down"}, "rate limit"),
        (anthropic.NotFoundError, {"message": "no model"}, "not found"),
        (anthropic.PermissionDeniedError, {"message": "nope"}, "lacks permission"),
        (anthropic.APIConnectionError, {"message": "offline"}, "Could not reach"),
        (anthropic.APIStatusError, {"message": "oops", "status_code": 503}, "API error"),
    ],
)
def test_sdk_errors_become_provider_errors(client_mock, exc_class, kwargs, expected):
    """Every SDK failure mode must be translated, so the caller can fall back."""
    client_mock.messages.create.side_effect = _api_error(exc_class, **kwargs)
    with pytest.raises(AIProviderError, match=expected):
        claude.chat("hello")


def test_unexpected_exceptions_are_also_contained(client_mock):
    client_mock.messages.create.side_effect = ValueError("something odd")
    with pytest.raises(AIProviderError, match="Unexpected AI error"):
        claude.chat("hello")
