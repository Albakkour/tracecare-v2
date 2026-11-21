from app.llm.demo_provider import DemoProvider
from app.llm.schemas import ExtractionOutput, FactCandidate, PatientExplanationOutput, PatientStatementCandidate
from app.services.checklist_service import get_templates
from app.services.pipeline import run_analysis
from app.services.samples import get_sample
from tests.conftest import SAMPLE_TRANSCRIPT


def analyze_demo(text=SAMPLE_TRANSCRIPT):
    return run_analysis(text, get_templates(["headache_demo_v1"]), DemoProvider())


def all_note_statements(result):
    return [s for section in result.clinical_note.sections for s in section.statements]


def test_negative_symptom_is_preserved_everywhere():
    r = analyze_demo()
    fever = next(f for f in r.facts if f.concept == "fever")
    assert fever.polarity == "negative"
    note = next(s for s in all_note_statements(r) if fever.fact_id in s.fact_ids)
    assert "absent" in note.text.lower() and note.section == "negatives"
    patient = next(s for s in r.patient_explanation.statements if fever.fact_id in s.fact_ids)
    assert "not" in patient.text.lower() and not patient.meaning_checks


def test_uncertain_medication_dosage_is_preserved():
    r = analyze_demo()
    dose = next(f for f in r.facts if f.concept == "medication dosage")
    assert dose.polarity == "uncertain"
    assert dose.supporting_quote == "Yes, but I don't remember the dosage."
    note = next(s for s in all_note_statements(r) if dose.fact_id in s.fact_ids)
    assert note.section == "uncertain" and "uncertain" in note.text.lower()
    patient = next(s for s in r.patient_explanation.statements if dose.fact_id in s.fact_ids)
    assert "not clear" in patient.text.lower()


def test_missing_information_is_not_converted_to_negative():
    r = analyze_demo()
    # Nausea was never discussed: it must not appear as a negative finding.
    assert not any("nausea" in f.concept for f in r.facts)
    onset = next(i for i in r.coverage_reports[0].items if i.item_id == "onset")
    assert onset.status == "not_found_in_transcript"
    gap = next(s for s in all_note_statements(r) if s.checklist_item_id == "onset")
    assert "not found in this transcript" in gap.text and "fail" not in gap.text.lower()


def test_demo_coverage_for_synthetic_sample():
    r = run_analysis(get_sample("synthetic_headache_basic")["transcript"], get_templates([]), DemoProvider())
    report = r.coverage_reports[0]
    statuses = {i.item_id: i.status for i in report.items}
    assert statuses["frequency_pattern"] == "asked_but_unanswered"
    assert statuses["duration_course"] == "volunteered_not_asked"
    assert statuses["location"] == "asked_and_addressed"
    assert (report.question_coverage.numerator, report.question_coverage.denominator) == (4, 8)
    assert (report.information_capture.numerator, report.information_capture.denominator) == (5, 8)


def test_every_output_reference_resolves():
    for sample_id in ("synthetic_headache_basic", "synthetic_headache_tricky", "aci_d2n040", "aci_d2n114"):
        r = run_analysis(get_sample(sample_id)["transcript"], get_templates([]), DemoProvider())
        fact_ids = {f.fact_id for f in r.facts}
        seg_ids = {s.segment_id for s in r.segments}
        for s in all_note_statements(r) + r.patient_explanation.statements:
            assert set(s.fact_ids) <= fact_ids
        for f in r.facts:
            assert set(f.source_segment_ids) <= seg_ids and f.evidence
        for report in r.coverage_reports:
            for item in report.items:
                assert set(item.clinician_question_segment_ids + item.information_segment_ids) <= seg_ids


def test_swapped_speaker_labels_create_pending_items():
    r = run_analysis(get_sample("aci_d2n114")["transcript"], get_templates([]), DemoProvider())
    assert r.coverage_reports[0].pending_review_count >= 1


def test_embedded_instruction_in_transcript_is_treated_as_data():
    r = run_analysis(get_sample("synthetic_headache_tricky")["transcript"], get_templates([]), DemoProvider())
    assert not any("antibiotic" in f.normalized_value.lower() for f in r.facts)


class FabricatingProvider(DemoProvider):
    """A mocked LLM that returns an unsupported fact and a statement citing an unknown fact."""

    def extract(self, segments, templates):
        out = super().extract(segments, templates)
        out.facts.append(FactCandidate(
            fact_id="F900", category="medication", concept="antibiotics", normalized_value="Prescribed antibiotics",
            polarity="positive", certainty="explicit", temporality="current", source_segment_ids=["S006"],
            supporting_quote="I was prescribed amoxicillin 500 mg."))
        return ExtractionOutput(facts=out.facts, symptoms=out.symptoms, checklist_assessments=out.checklist_assessments)

    def explain_for_patient(self, facts, language):
        out = super().explain_for_patient(facts, language)
        out.statements.append(PatientStatementCandidate(text="You need antibiotics.", fact_ids=["F900"]))
        return PatientExplanationOutput(statements=out.statements)


def test_unsupported_fact_from_mocked_llm_is_rejected_and_never_shown():
    r = run_analysis(SAMPLE_TRANSCRIPT, get_templates(["headache_demo_v1"]), FabricatingProvider())
    assert [f.fact_id for f in r.rejected_facts] == ["F900"]
    assert "F900" not in {f.fact_id for f in r.facts}
    texts = [s.text for s in all_note_statements(r) + r.patient_explanation.statements]
    assert not any("antibiotic" in t.lower() for t in texts)


def test_no_matching_template_returns_coverage_unavailable():
    r = run_analysis("Doctor: How is your knee?\nPatient: My knee pain is bad.", get_templates(["headache_demo_v1"]),
                     DemoProvider())
    assert r.coverage_reports[0].coverage_available is False
    assert "does not invent" in r.coverage_reports[0].message


# ------------------------------------------------------------------------------------------- API

def test_health_and_templates(client):
    assert client.get("/api/health").json()["status"] == "ok"
    templates = client.get("/api/templates").json()["templates"]
    t = next(t for t in templates if t["template_id"] == "headache_demo_v1")
    assert t["status"] == "demo_not_clinically_validated" and t["review_required"] is True


def test_demo_provider_works_without_api_credentials(client):
    config = client.get("/api/config").json()
    assert config["providers"] == ["demo"] and config["default_provider"] == "demo"
    resp = client.post("/api/analyze", json={"transcript": SAMPLE_TRANSCRIPT, "template_ids": ["headache_demo_v1"]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["provider"] == "demo" and body["persisted"] is True
    assert body["clinical_note"]["status"] == "draft_clinician_review_required"
    assert body["coverage_reports"][0]["question_coverage"]["denominator"] == 8


def test_anthropic_provider_without_key_gives_clear_error(client):
    resp = client.post("/api/analyze", json={"transcript": SAMPLE_TRANSCRIPT, "provider": "anthropic"})
    assert resp.status_code == 400
    assert "ANTHROPIC_API_KEY" in resp.json()["detail"]


def test_input_limits_and_validation(client):
    assert client.post("/api/analyze", json={"transcript": "x" * 40000}).status_code == 413
    assert client.post("/api/analyze", json={"transcript": "   "}).status_code == 422
    resp = client.post("/api/analyze", json={"transcript": SAMPLE_TRANSCRIPT, "template_ids": ["made_up_v9"]})
    assert resp.status_code == 400


def test_review_override_recalculates_and_persists(client):
    body = client.post("/api/analyze", json={"transcript": SAMPLE_TRANSCRIPT,
                                             "template_ids": ["headache_demo_v1"]}).json()
    enc = body["encounter_id"]
    before = body["coverage_reports"][0]
    assert before["question_coverage"]["denominator"] == 8

    # Not applicable requires a reason.
    url = f"/api/encounters/{enc}/coverage-items/location"
    assert client.patch(url, json={"status": "not_applicable"}).status_code == 422
    resp = client.patch(url, json={"status": "not_applicable", "not_applicable_reason": "Not relevant (test)."})
    after = resp.json()["coverage_reports"][0]
    assert after["question_coverage"]["denominator"] == 7
    assert after["not_applicable_count"] == 1
    item = next(i for i in after["items"] if i["item_id"] == "location")
    assert item["reviewed"] is True and item["not_applicable_reason"] == "Not relevant (test)."

    # The note's follow-up section no longer lists the excluded item.
    note_items = [s["checklist_item_id"] for sec in resp.json()["clinical_note"]["sections"] for s in sec["statements"]]
    assert "location" not in note_items

    # Reloading the encounter returns the reviewed state.
    reloaded = client.get(f"/api/encounters/{enc}").json()
    assert reloaded["coverage_reports"][0]["not_applicable_count"] == 1

    assert client.delete(f"/api/encounters/{enc}").status_code == 200
    assert client.get(f"/api/encounters/{enc}").status_code == 404


def test_demo_password_gate(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "letmein")
    get_settings.cache_clear()
    assert client.post("/api/analyze", json={"transcript": SAMPLE_TRANSCRIPT}).status_code == 401
    assert client.post("/api/session", json={"password": "wrong"}).status_code == 401
    token = client.post("/api/session", json={"password": "letmein"}).json()["token"]
    resp = client.post("/api/analyze", json={"transcript": SAMPLE_TRANSCRIPT},
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_rate_limit(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("ANALYSIS_RATE_LIMIT", "2/hour")
    get_settings.cache_clear()
    codes = [client.post("/api/analyze", json={"transcript": SAMPLE_TRANSCRIPT}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
