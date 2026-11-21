"""Clinical note rendered from validated facts with controlled templates (no LLM).

Polarity and uncertainty are rendered deterministically from structured fields, so a negative or
uncertain fact can never be phrased as a confirmed positive. No diagnoses, examination findings,
or plans are generated.
"""

from __future__ import annotations

from app.schemas.coverage import CoverageReport
from app.schemas.facts import CLINICIAN_CATEGORIES, MedicalFact, SymptomMention
from app.schemas.outputs import ClinicalNote, GeneratedStatement, NoteSection

PATIENT_REPORTED_POSITIVE = {"symptom", "impact", "duration", "frequency"}
HISTORY_CATEGORIES = {"history", "allergy", "social"}


def _cap(text: str) -> str:
    text = text.strip()
    return text[:1].upper() + text[1:] if text else text


def _end(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def fact_details(fact: MedicalFact) -> str:
    """Qualifiers (duration, location, ...) that are not already stated in normalized_value."""
    base = fact.normalized_value.lower()
    parts = []
    for label, value in (("duration", fact.duration), ("frequency", fact.frequency), ("severity", fact.severity),
                         ("location", fact.location), ("context", fact.context)):
        if value and value.lower() not in base:
            parts.append(f"{label}: {value}")
    return f" ({'; '.join(parts)})" if parts else ""


def render_fact(fact: MedicalFact) -> str:
    phrase = _cap(fact.normalized_value) + fact_details(fact)
    if fact.evidence_status == "needs_review":
        reason = fact.review_notes[0] if fact.review_notes else "evidence needs review"
        return f"{_end(phrase)[:-1]} — needs review: {reason.rstrip('.')}."
    if fact.polarity == "negative":
        return f"{_cap(fact.concept)}: reported as absent ({fact.normalized_value.rstrip('.')})."
    if fact.polarity == "uncertain":
        return f"{_end(phrase)[:-1]} — uncertain / not established."
    return _end(phrase)


def _primary_symptom(facts: list[MedicalFact], trigger_concepts: set[str]) -> MedicalFact | None:
    candidates = [f for f in facts if f.category == "symptom" and f.polarity == "positive"
                  and f.evidence_status == "source_linked"]
    for f in candidates:
        if any(t in f.concept.lower() for t in trigger_concepts):
            return f
    return candidates[0] if candidates else None


def render_clinician_fact(fact: MedicalFact) -> str:
    """Clinician statements are documented as stated, keeping hedges such as "may be"."""
    text = _end(_cap(fact.normalized_value))
    if fact.evidence_status == "needs_review":
        reason = fact.review_notes[0] if fact.review_notes else "evidence needs review"
        return f"{text[:-1]} — needs review: {reason.rstrip('.')}."
    return text


def generate_clinical_note(facts: list[MedicalFact], coverage_reports: list[CoverageReport],
                           trigger_concepts: set[str] | None = None,
                           symptoms: list[SymptomMention] | None = None) -> ClinicalNote:
    mentions = list(symptoms or [])
    counter = iter(range(1, 10_000))

    def stmt(section: str, text: str, fact_ids: list[str], needs_review: bool = False,
             item_id: str | None = None, notes: list[str] | None = None) -> GeneratedStatement:
        return GeneratedStatement(statement_id=f"N{next(counter):03d}", section=section, text=text,
                                  fact_ids=fact_ids, checklist_item_id=item_id,
                                  kind="coverage_gap" if item_id else "fact", needs_review=needs_review,
                                  review_notes=notes or [])

    clinician_facts = [f for f in facts if f.category in CLINICIAN_CATEGORIES and f.evidence_status != "rejected"]
    patient_facts = [f for f in facts if f.category not in CLINICIAN_CATEGORIES]
    linked = [f for f in patient_facts if f.evidence_status == "source_linked"]
    review = [f for f in patient_facts if f.evidence_status == "needs_review"]
    primary = _primary_symptom(patient_facts, {t.lower() for t in (trigger_concepts or set())})
    used: set[str] = set()

    chief: list[GeneratedStatement] = []
    if primary:
        rendered = render_fact(primary)
        chief.append(stmt("chief_concern", f"Patient reports {rendered[:1].lower()}{rendered[1:]}", [primary.fact_id]))
        used.add(primary.fact_id)

    def section_facts(pred) -> list[MedicalFact]:
        out = [f for f in linked if f.fact_id not in used and pred(f)]
        used.update(f.fact_id for f in out)
        return out

    negatives = section_facts(lambda f: f.polarity == "negative")
    uncertain = section_facts(lambda f: f.polarity == "uncertain")
    symptoms = section_facts(lambda f: f.category in PATIENT_REPORTED_POSITIVE)
    medications = section_facts(lambda f: f.category == "medication")
    history = section_facts(lambda f: f.category in HISTORY_CATEGORIES)
    other = section_facts(lambda f: True)

    def fact_statements(section: str, items: list[MedicalFact]) -> list[GeneratedStatement]:
        return [stmt(section, render_fact(f), [f.fact_id], needs_review=f.evidence_status == "needs_review",
                     notes=f.review_notes) for f in items]

    def clinician_statements(section: str, categories: set[str]) -> list[GeneratedStatement]:
        return [stmt(section, render_clinician_fact(f), [f.fact_id], needs_review=f.evidence_status == "needs_review",
                     notes=f.review_notes) for f in clinician_facts if f.category in categories]

    gaps: list[GeneratedStatement] = []
    fact_index = {f.fact_id: f for f in facts}
    for sym in mentions:
        if sym.followed_up is False:
            ids = [i for i in sym.fact_ids if i in fact_index]
            gaps.append(stmt("follow_up", f"{_cap(sym.concept)}: mentioned by the patient; no clinician question or "
                                          "response about it was found (review).", ids, needs_review=True))
    multi = sum(1 for r in coverage_reports if r.items) > 1
    for report in coverage_reports:
        if not report.coverage_available and not report.items:
            continue
        short = (report.template_name or "").replace(" — consultation documentation demo", "")
        prefix = f"{short} — " if multi and short else ""
        for item in report.items:
            if item.status == "not_found_in_transcript":
                gaps.append(stmt("follow_up", f"{prefix}{item.label}: not found in this transcript (provisional — review).",
                                 [], item_id=item.item_id))
            elif item.status == "unclear_needs_review":
                gaps.append(stmt("follow_up", f"{prefix}{item.label}: pending review — evidence or classification unclear.",
                                 [], needs_review=True, item_id=item.item_id))

    sections = [
        NoteSection(section_id="chief_concern", heading="Reason for consultation / chief concern", statements=chief),
        NoteSection(section_id="symptoms", heading="Symptoms reported", statements=fact_statements("symptoms", symptoms)),
        NoteSection(section_id="negatives", heading="Relevant negatives explicitly discussed",
                    statements=fact_statements("negatives", negatives)),
        NoteSection(section_id="medications", heading="Medication information mentioned",
                    statements=fact_statements("medications", medications)),
        NoteSection(section_id="history", heading="Relevant history mentioned",
                    statements=fact_statements("history", history + other)),
        NoteSection(section_id="examination", heading="Examination findings (as stated by the clinician)",
                    statements=clinician_statements("examination", {"examination"}),
                    empty_message="No examination findings were stated in this transcript."),
        NoteSection(section_id="assessment", heading="Clinician's assessment (as stated)",
                    statements=clinician_statements("assessment", {"assessment"}),
                    empty_message="No assessment was stated in this transcript."),
        NoteSection(section_id="plan", heading="Plan, prescriptions and advice (as stated)",
                    statements=clinician_statements("plan", {"plan", "prescription", "advice"}),
                    empty_message="No plan or advice was stated in this transcript."),
        NoteSection(section_id="clinician_follow_up", heading="Follow-up and safety-netting advice (as stated)",
                    statements=clinician_statements("clinician_follow_up", {"follow_up"}),
                    empty_message="No follow-up arrangements were stated in this transcript."),
        NoteSection(section_id="uncertain", heading="Uncertain, incomplete, or needs-review information",
                    statements=fact_statements("uncertain", uncertain + review),
                    empty_message="No uncertain items were identified."),
        NoteSection(section_id="follow_up", heading="Potential gaps: topics not found and symptoms not followed up",
                    statements=gaps,
                    empty_message="No checklist template applied, or no topics were flagged."),
    ]
    return ClinicalNote(sections=sections)
