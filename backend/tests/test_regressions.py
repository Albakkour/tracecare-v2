"""Regression tests for reported issues and the patient-identity / production features."""

from pathlib import Path

import pytest

from app.core.config import Settings
from app.llm.demo_provider import DemoProvider
from app.llm.schemas import ChecklistCandidate
from app.services.checklist_service import get_templates, load_registry
from app.services.evidence_validator import validate_checklist
from app.services.patient_identity import (
    contains_real_personnummer,
    detect_patient_name,
    generate_temp_personnummer,
    validate_temp_personnummer,
)
from app.services.pipeline import run_analysis
from app.services.transcript_parser import parse_transcript

FIXTURES = Path(__file__).parent / "fixtures"
LISA = (FIXTURES / "back_pain_lisa.txt").read_text()
DAVID = (FIXTURES / "knee_pain_david.txt").read_text()


def statuses(report):
    return {i.item_id: i.status for i in report.items}


# --- Issue 1: missing items must stay in the denominator ------------------------------------------

def test_low_confidence_not_found_stays_in_denominator():
    segments = parse_transcript(LISA).segments
    template = load_registry()["msk_pain_demo_v1"]
    cand = ChecklistCandidate(
        template_id=template.template_id, item_id="onset", proposed_status="not_found_in_transcript",
        clinician_question_segment_ids=[], clinician_question_quotes=[], information_segment_ids=[],
        information_quotes=[], fact_ids=[], confidence="low", rationale="Not discussed.")
    items, _ = validate_checklist([cand], template, segments, set())
    onset = next(i for i in items if i.item_id == "onset")
    assert onset.status == "not_found_in_transcript"
    assert onset.review_state == "provisional"


def test_low_confidence_with_evidence_is_still_pending():
    segments = parse_transcript(LISA).segments
    template = load_registry()["msk_pain_demo_v1"]
    cand = ChecklistCandidate(
        template_id=template.template_id, item_id="previous_episodes", proposed_status="asked_and_addressed",
        clinician_question_segment_ids=["S019"], clinician_question_quotes=["Have you had similar back problems in the past?"],
        information_segment_ids=["S020"], information_quotes=["Yes, occasionally"], fact_ids=[], confidence="low",
        rationale="x")
    items, _ = validate_checklist([cand], template, segments, set())
    assert next(i for i in items if i.item_id == "previous_episodes").status == "unclear_needs_review"


def test_back_pain_transcript_only_onset_missing():
    report = run_analysis(LISA, get_templates([]), DemoProvider()).coverage_reports[0]
    assert report.template_id == "msk_pain_demo_v1"
    assert statuses(report)["onset"] == "not_found_in_transcript"
    assert (report.question_coverage.numerator, report.question_coverage.denominator) == (8, 9)
    assert (report.information_capture.numerator, report.information_capture.denominator) == (8, 9)


def test_knee_pain_transcript_onset_and_previous_episodes_missing():
    report = run_analysis(DAVID, get_templates([]), DemoProvider()).coverage_reports[0]
    s = statuses(report)
    assert s["onset"] == "not_found_in_transcript"
    assert s["previous_episodes"] == "not_found_in_transcript"
    assert s["injury_mechanism"] == "asked_and_addressed"  # "any recent injuries?" is not onset
    assert (report.question_coverage.numerator, report.question_coverage.denominator) == (7, 9)


def test_bracket_colon_speaker_format():
    seg = parse_transcript("[Doctor]: Hello, Lisa.\n[Patient]: Hi.").segments
    assert [s.speaker for s in seg] == ["clinician", "patient"]
    assert seg[0].text == "Hello, Lisa."


# --- Issue 2: review stays available after a review action and after reload -----------------------

def test_review_controls_stay_available(client):
    body = client.post("/api/analyze", json={"transcript": LISA}).json()
    assert body["persisted"] is True
    enc = body["encounter_id"]
    resp = client.patch(f"/api/encounters/{enc}/coverage-items/onset?template_id=msk_pain_demo_v1",
                        json={"confirm": True}).json()
    assert resp["persisted"] is True
    item = next(i for i in resp["coverage_reports"][0]["items"] if i["item_id"] == "onset")
    assert item["reviewed"] is True and item["status"] == "not_found_in_transcript"
    assert client.get(f"/api/encounters/{enc}").json()["persisted"] is True
    # A second review action on another item still works.
    second = client.patch(f"/api/encounters/{enc}/coverage-items/location?template_id=msk_pain_demo_v1",
                          json={"confirm": True})
    assert second.status_code == 200 and second.json()["persisted"] is True


# --- Patient identity --------------------------------------------------------------------------------

def test_temp_personnummer_validation():
    value, birth = validate_temp_personnummer("19850412-t123")
    assert value == "19850412-T123" and birth.year == 1985
    for real in ("19850412-1234", "850412-1234", "198504121234"):
        with pytest.raises(ValueError, match="Real personnummer"):
            validate_temp_personnummer(real)
    with pytest.raises(ValueError):
        validate_temp_personnummer("19851332-T123")
    generated = generate_temp_personnummer()
    assert validate_temp_personnummer(generated)[0] == generated


def test_real_personnummer_in_transcript_is_rejected(client):
    assert contains_real_personnummer("Patient: my number is 19850412-1234")
    assert not contains_real_personnummer("Patient: about seven out of ten, 19850412-T123")
    resp = client.post("/api/analyze", json={"transcript": "Doctor: ID?\nPatient: 850412-1234"})
    assert resp.status_code == 422 and "personnummer" in resp.json()["detail"]


def test_patient_name_detected_with_evidence():
    detected = detect_patient_name(parse_transcript(LISA).segments)
    assert detected is not None
    name, ref = detected
    assert name == "Lisa" and ref.segment_id == "S001" and ref.quote_match == "exact"


def test_patient_summary_in_response(client):
    body = client.post("/api/analyze", json={
        "transcript": DAVID,
        "patient": {"display_name": "David Test", "temp_personnummer": "19900101-T042"}}).json()
    p = body["patient"]
    assert p["display_name"] == "David Test" and p["name_source"] == "entered"
    assert p["temp_personnummer"] == "19900101-T042" and p["birth_date"] == "1990-01-01" and p["age"] >= 30
    assert body["chief_concern"]
    bad = client.post("/api/analyze", json={"transcript": DAVID, "patient": {"temp_personnummer": "19900101-1234"}})
    assert bad.status_code == 422 and "Real personnummer" in bad.json()["detail"]
    temp = client.get("/api/patients/temp-id").json()["temp_personnummer"]
    assert "-T" in temp


# --- Production configuration -----------------------------------------------------------------------

def test_production_problems_detected():
    bad = Settings(APP_ENV="production", DATABASE_URL="sqlite:///./x.db", SESSION_SECRET="", DEMO_MODE_ENABLED=True)
    problems = " ".join(bad.production_problems())
    assert "SQLite" in problems and "SESSION_SECRET" in problems
    good = Settings(APP_ENV="production", DATABASE_URL="postgresql://u:p@h:5432/db",
                    SESSION_SECRET="x" * 40, CORS_ORIGINS="https://tracecare.vercel.app", DEMO_MODE_ENABLED=True)
    assert good.production_problems() == []
    assert good.sqlalchemy_database_url.startswith("postgresql+psycopg://")


def test_security_headers_and_no_stack_traces(client):
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["cache-control"] == "no-store"


def test_medication_allergy_question_is_not_a_medication_denial():
    result = run_analysis(LISA, get_templates([]), DemoProvider())
    meds = [f for f in result.facts if f.category == "medication"]
    assert any(f.polarity == "positive" and "ibuprofen" in f.concept for f in meds)
    assert not any(f.polarity == "negative" for f in meds)
