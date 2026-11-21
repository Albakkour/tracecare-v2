"""Claude provider tests against a mocked HTTP transport. No live API calls, no credentials needed."""

import json

import anthropic
import httpx2
import pytest

from app.core.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ProviderError
from app.services.checklist_service import get_templates
from app.services.pipeline import run_analysis
from tests.conftest import SAMPLE_TRANSCRIPT

EXTRACTION = {
    "facts": [
        {"fact_id": "F001", "category": "symptom", "concept": "headache", "normalized_value": "Headache for three days",
         "polarity": "positive", "certainty": "explicit", "temporality": "current", "duration": "three days",
         "frequency": None, "severity": None, "location": None, "context": None,
         "source_segment_ids": ["S002"], "supporting_quote": "I've had a headache for three days."},
        {"fact_id": "F002", "category": "symptom", "concept": "fever", "normalized_value": "No fever",
         "polarity": "negative", "certainty": "explicit", "temporality": "current", "duration": None,
         "frequency": None, "severity": None, "location": None, "context": None,
         "source_segment_ids": ["S003", "S004"], "supporting_quote": "No, I haven't had a fever."},
    ],
    "symptoms": [{"concept": "headache", "polarity": "positive", "fact_ids": ["F001"], "source_segment_ids": ["S002"],
                  "supporting_quote": "I've had a headache for three days.", "template_id": "headache_demo_v1"}],
    "checklist_assessments": [
        {"template_id": "headache_demo_v1", "item_id": "other_symptoms", "proposed_status": "asked_and_addressed",
         "clinician_question_segment_ids": ["S003"], "clinician_question_quotes": ["Have you had a fever?"],
         "information_segment_ids": ["S004"], "information_quotes": ["No, I haven't had a fever."],
         "fact_ids": ["F002"], "confidence": "high", "rationale": "Asked about fever."},
    ],
}
PATIENT = {"statements": [
    {"text": "You said you have had a headache for three days.", "fact_ids": ["F001"]},
    {"text": "You said you have not had a fever.", "fact_ids": ["F002"]},
]}


def message(payload: dict, stop_reason: str = "end_turn") -> dict:
    return {
        "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "stop_reason": stop_reason, "stop_sequence": None,
        "usage": {"input_tokens": 10, "output_tokens": 10},
    }


def provider_with(handler) -> AnthropicProvider:
    settings = Settings(ANTHROPIC_API_KEY="test-key", ANTHROPIC_MODEL="claude-opus-5-5")
    p = AnthropicProvider(settings)
    p._client = anthropic.Anthropic(api_key="test-key", max_retries=0,
                                    http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    return p


def test_full_pipeline_with_mocked_claude():
    requests = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        requests.append((request, body))
        payload = EXTRACTION if "<transcript>" in body["messages"][0]["content"] else PATIENT
        return httpx2.Response(200, json=message(payload))

    result = run_analysis(SAMPLE_TRANSCRIPT, get_templates(["headache_demo_v1"]), provider_with(handler))

    extract_req, extract_body = requests[0]
    assert extract_body["model"] == "claude-opus-5-5"
    assert extract_body["output_config"]["format"]["type"] == "json_schema"
    assert extract_body["output_config"]["effort"] == "medium"
    assert extract_body["fallbacks"] == "default"
    assert "server-side-fallback" in extract_req.headers["anthropic-beta"]
    assert "untrusted DATA" in extract_body["system"]
    # Patient explanation request only receives accepted facts, not the transcript.
    assert "<transcript>" not in requests[1][1]["messages"][0]["content"]

    assert [f.fact_id for f in result.facts] == ["F001", "F002"]
    assert result.provider == "anthropic" and result.model == "claude-opus-5-5"
    report = result.coverage_reports[0]
    assert report.question_coverage.numerator == 1 and report.question_coverage.denominator == 8
    assert [s.fact_ids for s in result.patient_explanation.statements] == [["F001"], ["F002"]]
    assert not any(s.meaning_checks for s in result.patient_explanation.statements)


@pytest.mark.parametrize("status,kind", [(401, "auth"), (429, "rate_limit"), (404, "model"), (500, "api_error")])
def test_api_errors_become_clear_provider_errors(status, kind):
    def handler(request):
        return httpx2.Response(status, json={"type": "error", "error": {"type": "x", "message": "x"}})

    with pytest.raises(ProviderError) as exc:
        provider_with(handler).extract([], [])
    assert exc.value.kind == kind


def test_malformed_output_is_rejected():
    def handler(request):
        return httpx2.Response(200, json=message({"facts": "not-a-list"}))

    with pytest.raises(ProviderError) as exc:
        provider_with(handler).extract([], [])
    assert exc.value.kind == "malformed_output"


def test_truncated_output_is_reported():
    def handler(request):
        return httpx2.Response(200, json=message(EXTRACTION, stop_reason="max_tokens"))

    with pytest.raises(ProviderError) as exc:
        provider_with(handler).extract([], [])
    assert exc.value.kind in {"truncated", "malformed_output"}


def test_timeout_is_reported():
    def handler(request):
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(ProviderError) as exc:
        provider_with(handler).extract([], [])
    assert exc.value.kind == "timeout"
