"""Tests for: 21-template registry, clinician statements, after-visit summary, follow-up detection,
meaning-check fixes (incl. Swedish), record explainer, and evaluation endpoint."""

from pathlib import Path

from app.llm.demo_provider import DIM_CUES, DemoProvider
from app.llm.schemas import FactCandidate, RecordSimplificationOutput, RecordStatementCandidate
from app.schemas.facts import MedicalFact
from app.services.checklist_service import get_templates, load_registry
from app.services.evidence_validator import validate_facts
from app.services.meaning import fact_meaning_checks, text_meaning_checks
from app.services.pipeline import run_analysis
from app.services.record_explainer import explain_record, split_record
from app.services.transcript_parser import parse_transcript

OMAR = (Path(__file__).parent / "fixtures" / "stomach_pain_omar.txt").read_text()


def fact(**kw) -> MedicalFact:
    base = dict(fact_id="F001", category="symptom", concept="appetite", normalized_value="not very hungry",
                polarity="positive", certainty="explicit", temporality="current", source_segment_ids=["S002"],
                supporting_quote="I also don't feel very hungry")
    base.update(kw)
    return MedicalFact(**base)


# --- templates -----------------------------------------------------------------------------------------

def test_registry_has_20_specific_templates_plus_general():
    reg = load_registry()
    assert len(reg) == 21 and "general_symptom_demo_v1" in reg
    for t in reg.values():
        assert t.status == "demo_not_clinically_validated"
        for item in t.items:
            assert item.dimension in DIM_CUES, (t.template_id, item.item_id)


def test_vomiting_and_stomach_pain_get_their_own_templates():
    r = run_analysis(OMAR, get_templates([]), DemoProvider())
    assert [c.template_id for c in r.coverage_reports] == ["abdominal_pain_demo_v1", "nausea_vomiting_demo_v1"]


def test_unmatched_main_symptom_uses_general_template():
    t = "Doctor: What brings you in?\nPatient: I've had a lump on my arm for two weeks.\nDoctor: Is it painful?\nPatient: No."
    provider = DemoProvider()
    # 'lump' is not in any specific template; add it to the demo lexicon on the fly for this test.
    import re
    from app.llm import demo_provider as dp
    dp.SYMPTOMS.append(("lump", re.compile(r"\blump\b", re.I)))
    try:
        r = run_analysis(t, get_templates([]), provider)
    finally:
        dp.SYMPTOMS.pop()
    assert r.coverage_reports[0].template_id == "general_symptom_demo_v1"


# --- clinician statements & after-visit summary -----------------------------------------------------------

def test_clinician_statements_are_extracted_and_rendered():
    r = run_analysis(OMAR, get_templates([]), DemoProvider())
    cats = {f.category for f in r.facts}
    assert {"examination", "assessment", "prescription", "advice", "follow_up"} <= cats
    exam = next(f for f in r.facts if "37.8" in f.normalized_value)
    assert exam.category == "examination"  # decimal number not split
    sections = {s.section_id: s for s in r.clinical_note.sections}
    assert sections["plan"].statements and sections["clinician_follow_up"].statements
    pe = r.patient_explanation
    assert {"your_concern", "what_you_told", "findings", "assessment", "plan", "follow_up"} <= {s.section for s in pe.statements}
    assert "What the doctor found" in pe.plain_text and "ondansetron 4 mg" in pe.plain_text
    assert pe.plain_text.startswith("After-visit summary — Omar")


def test_clinician_category_from_patient_turn_needs_review():
    segs = parse_transcript("Doctor: Any pain?\nPatient: I think it's a stomach infection.").segments
    usable, _, findings = validate_facts([FactCandidate(
        fact_id="F001", category="assessment", concept="assessment", normalized_value="stomach infection",
        polarity="uncertain", certainty="explicit", temporality="current", source_segment_ids=["S002"],
        supporting_quote="I think it's a stomach infection.")], segs)
    assert usable[0].evidence_status == "needs_review"
    assert any(f.code == "speaker_mismatch" for f in findings)


def test_symptom_nobody_followed_up_is_flagged():
    r = run_analysis(OMAR, get_templates([]), DemoProvider())
    sleep = next(s for s in r.symptoms if s.concept == "trouble sleeping")
    assert sleep.followed_up is False
    assert any(f.code == "unexplored_symptom" and "trouble sleeping" in f.message for f in r.validation_findings)
    gaps = next(s for s in r.clinical_note.sections if s.section_id == "follow_up").statements
    assert any("Trouble sleeping" in g.text for g in gaps)
    assert next(s for s in r.symptoms if s.concept == "abdominal pain").followed_up is True


def test_swedish_requested_with_demo_warns():
    r = run_analysis(OMAR, get_templates([]), DemoProvider(), language="sv")
    assert r.patient_explanation.language == "en"
    assert any("Swedish" in w for w in r.warnings)


# --- meaning checks ----------------------------------------------------------------------------------------

def test_negation_in_positive_finding_is_not_a_false_alarm():
    assert fact_meaning_checks("You are not very hungry right now.", [fact()]) == []


def test_swedish_meaning_checks():
    denied = fact(concept="fever", normalized_value="No fever", polarity="negative", supporting_quote="No fever.")
    assert fact_meaning_checks("Du har inte haft feber.", [denied], "sv") == []
    assert [c.check for c in fact_meaning_checks("Du har haft feber.", [denied], "sv")] == ["negation"]
    pain = fact(concept="pain", normalized_value="pain for three days", duration="three days", supporting_quote="x")
    assert fact_meaning_checks("Du har haft ont i tre dagar.", [pain], "sv") == []


def test_text_meaning_checks_for_records():
    assert [c.check for c in text_meaning_checks("Denies chest pain.", "You have chest pain.")] == ["negation"]
    assert [c.check for c in text_meaning_checks("Possible appendicitis.", "You have appendicitis.")] == ["uncertainty"]
    assert [c.check for c in text_meaning_checks("Ondansetron 4 mg BID.", "Ondansetron 8 mg twice a day.")] == ["number"]
    assert text_meaning_checks("Temperature 3,000 units.", "3000 units") == []


# --- record explainer ---------------------------------------------------------------------------------------

RECORD = "HISTORY:\nPatient denies fever. Temperature 37.8 C.\nASSESSMENT\nPossible gastroenteritis.\n- Follow-up in 1 week."


def test_record_split_keeps_headings_and_decimals():
    sents = split_record(RECORD)
    assert [s.text for s in sents] == ["Patient denies fever.", "Temperature 37.8 C.", "Possible gastroenteritis.",
                                        "Follow-up in 1 week."]
    assert sents[0].heading == "History" and sents[2].heading == "Assessment"
    for s in sents:
        assert RECORD[s.start_char:s.end_char] == s.text


class LossyProvider(DemoProvider):
    """Drops a negation, a hedge and a whole sentence."""

    def simplify_record(self, sentences, language):
        return RecordSimplificationOutput(statements=[
            RecordStatementCandidate(source_sentence_ids=["R001"], text="You have a fever."),
            RecordStatementCandidate(source_sentence_ids=["R003"], text="You have a stomach bug."),
            RecordStatementCandidate(source_sentence_ids=["R004"], text="Come back in one week."),
            RecordStatementCandidate(source_sentence_ids=["R999"], text="Invented sentence."),
        ])


def test_record_explainer_flags_meaning_changes_and_missing_content():
    r = explain_record(RECORD, LossyProvider())
    risks = {st.source_sentence_ids[0]: st.risk for st in r.statements}
    assert risks["R001"] == "high" and risks["R003"] == "medium" and risks["R004"] == "low"
    assert r.unexplained_sentence_ids == ["R002"]
    assert not any("Invented" in st.text for st in r.statements)
    assert any("no plain-language version" in w for w in r.warnings)


def test_record_endpoints(client):
    records = client.get("/api/record-samples").json()["records"]
    assert records and records[0]["record_id"] == "synthetic_note_omar"
    resp = client.post("/api/explain-record", json={"text": records[0]["text"], "provider": "demo"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["statements"] and body["plain_text"].startswith("Your record in plain language")
    bad = client.post("/api/explain-record", json={"text": "Patient 19850412-1234 denies fever."})
    assert bad.status_code == 422


def test_evaluation_endpoint(client):
    body = client.get("/api/evaluation").json()
    assert body["aci"]["human_transcripts"]["statements_resolving_pct"] == 100.0
    assert body["plaba"]["corruption_detection"]["negation_removed"]["detected_pct"] >= 90


def test_reduction_words_are_not_added_negations():
    assert text_meaning_checks("Reports reduced appetite.", "You do not feel as hungry as usual.") == []
    reduced = fact(normalized_value="reduced appetite", supporting_quote="my appetite is reduced")
    assert fact_meaning_checks("You are not as hungry as usual.", [reduced]) == []
