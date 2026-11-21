from app.llm.schemas import ChecklistCandidate, FactCandidate, PatientExplanationOutput, PatientStatementCandidate
from app.services.checklist_service import load_registry
from app.services.evidence_validator import locate_quote, validate_checklist, validate_facts
from app.services.patient_explainer import meaning_checks, validate_patient_statements


def fact(**kw) -> FactCandidate:
    base = dict(fact_id="F001", category="symptom", concept="headache", normalized_value="Headache",
                polarity="positive", certainty="explicit", temporality="current", duration="three days",
                source_segment_ids=["S002"], supporting_quote="I've had a headache for three days.")
    base.update(kw)
    return FactCandidate(**base)


def checklist(**kw) -> ChecklistCandidate:
    base = dict(template_id="headache_demo_v1", item_id="other_symptoms", proposed_status="asked_and_addressed",
                clinician_question_segment_ids=["S003"], clinician_question_quotes=["Have you had a fever?"],
                information_segment_ids=["S004"], information_quotes=["No, I haven't had a fever."],
                fact_ids=[], confidence="high", rationale="test")
    base.update(kw)
    return ChecklistCandidate(**base)


def test_exact_quote_is_source_linked_with_offsets(segments):
    usable, rejected, _ = validate_facts([fact()], segments)
    assert not rejected
    f = usable[0]
    assert f.evidence_status == "source_linked"
    ev = f.evidence[0]
    assert ev.quote_match == "exact"
    seg = segments[1]
    assert seg.text[ev.start_char - seg.start_char:ev.end_char - seg.start_char] == f.supporting_quote


def test_quote_not_in_referenced_segment_is_rejected(segments):
    usable, rejected, findings = validate_facts([fact(supporting_quote="I've had a migraine for a week.")], segments)
    assert not usable and rejected[0].evidence_status == "rejected"
    assert any(f.code == "fact_rejected" for f in findings)


def test_quote_from_a_different_segment_is_rejected(segments):
    # Quote exists in the transcript (S004) but the fact cites S002.
    _, rejected, _ = validate_facts([fact(supporting_quote="No, I haven't had a fever.")], segments)
    assert rejected


def test_whitespace_normalized_fallback_preserves_original_quote(segments):
    quote = "I’ve had a   headache for three days."
    usable, _, _ = validate_facts([fact(supporting_quote=quote)], segments)
    assert usable[0].evidence[0].quote_match == "normalized"
    assert usable[0].supporting_quote == quote.strip()


def test_invalid_source_id_is_rejected(segments):
    usable, rejected, findings = validate_facts([fact(source_segment_ids=["S999"])], segments)
    assert not usable
    assert "Unknown source segment" in rejected[0].review_notes[0]


def test_partially_unknown_source_id_needs_review(segments):
    usable, _, _ = validate_facts([fact(source_segment_ids=["S002", "S999"])], segments)
    assert usable[0].evidence_status == "needs_review"
    assert usable[0].source_segment_ids == ["S002"]


def test_speaker_mismatch_is_flagged(segments):
    # A patient symptom sourced only to the doctor's question.
    usable, _, findings = validate_facts(
        [fact(concept="fever", normalized_value="Fever", source_segment_ids=["S003"],
              supporting_quote="Have you had a fever?", duration=None)], segments)
    assert usable[0].evidence_status == "needs_review"
    assert any(f.code == "speaker_mismatch" for f in findings)


def test_duplicate_fact_ids_are_rejected(segments):
    second = fact(concept="fever", normalized_value="No fever", polarity="negative", source_segment_ids=["S004"],
                  supporting_quote="No, I haven't had a fever.", duration=None)
    usable, rejected, _ = validate_facts([fact(), second], segments)
    assert len(usable) == 1 and len(rejected) == 1
    assert "Duplicate" in rejected[0].review_notes[0]


def test_inferred_fact_is_not_presented_as_confirmed(segments):
    usable, _, _ = validate_facts([fact(certainty="inferred")], segments)
    assert usable[0].evidence_status == "needs_review"


def test_unknown_checklist_item_is_rejected(segments):
    template = load_registry()["headache_demo_v1"]
    items, findings = validate_checklist([checklist(item_id="red_flags")], template, segments, set())
    assert any(f.code == "unknown_checklist_item" for f in findings)
    assert {i.item_id for i in items} == template.item_ids()
    assert all(i.status == "not_found_in_transcript" for i in items)


def test_checklist_question_attributed_to_patient_turn_needs_review(segments):
    template = load_registry()["headache_demo_v1"]
    cand = checklist(clinician_question_segment_ids=["S004"], clinician_question_quotes=["No, I haven't had a fever."])
    items, _ = validate_checklist([cand], template, segments, set())
    item = next(i for i in items if i.item_id == "other_symptoms")
    assert item.status == "unclear_needs_review"
    assert any("speaker mismatch" in n for n in item.validation_notes)


def test_checklist_valid_evidence_keeps_proposed_status(segments):
    template = load_registry()["headache_demo_v1"]
    items, _ = validate_checklist([checklist()], template, segments, set())
    item = next(i for i in items if i.item_id == "other_symptoms")
    assert item.status == "asked_and_addressed"
    assert item.question_evidence[0].segment_id == "S003"


def test_checklist_status_disagreeing_with_evidence_needs_review(segments):
    template = load_registry()["headache_demo_v1"]
    items, _ = validate_checklist([checklist(proposed_status="volunteered_not_asked")], template, segments, set())
    assert next(i for i in items if i.item_id == "other_symptoms").status == "unclear_needs_review"


def test_provider_cannot_mark_item_not_applicable(segments):
    template = load_registry()["headache_demo_v1"]
    items, _ = validate_checklist([checklist(proposed_status="not_applicable")], template, segments, set())
    assert next(i for i in items if i.item_id == "other_symptoms").status == "unclear_needs_review"


def test_generated_statement_cannot_cite_unknown_fact(segments):
    usable, _, _ = validate_facts([fact()], segments)
    output = PatientExplanationOutput(statements=[
        PatientStatementCandidate(text="You have had a headache for three days.", fact_ids=["F001"]),
        PatientStatementCandidate(text="You were prescribed antibiotics.", fact_ids=["F042"]),
        PatientStatementCandidate(text="Unsupported sentence.", fact_ids=[]),
    ])
    statements, findings = validate_patient_statements(output, usable)
    assert [s.fact_ids for s in statements] == [["F001"]]
    assert sum(f.code == "statement_unknown_fact" for f in findings) == 2


def test_meaning_checks_flag_lost_negation_and_changed_number(segments):
    usable, _, _ = validate_facts([
        fact(),
        fact(fact_id="F002", concept="fever", normalized_value="No fever", polarity="negative",
             source_segment_ids=["S004"], supporting_quote="No, I haven't had a fever.", duration=None),
    ], segments)
    by_id = {f.fact_id: f for f in usable}
    assert [c.check for c in meaning_checks("You had a fever.", [by_id["F002"]])] == ["negation"]
    assert [c.check for c in meaning_checks("You have had a headache for two days.", [by_id["F001"]])] == ["number"]
    assert meaning_checks("You have had a headache for 3 days.", [by_id["F001"]]) == []


def test_locate_quote_rejects_empty_quote(segments):
    assert locate_quote("   ", segments[0]).quote_match == "not_found"
