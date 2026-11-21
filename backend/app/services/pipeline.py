"""The TraceCare analysis pipeline: parse -> propose -> validate -> calculate -> generate."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.llm.base import LLMProvider
from app.schemas.coverage import ChecklistTemplate, CoverageReport
from app.schemas.facts import MedicalFact
from app.schemas.outputs import AnalyzeResponse, PatientExplanation, PatientInfo, PatientSummary, ValidationFinding
from app.services import evidence_validator as ev
from app.services.coverage_calculator import calculate_coverage, no_template_report
from app.services.note_generator import generate_clinical_note
from app.services.patient_explainer import (
    DISCLAIMERS,
    INTROS,
    SECTION_HEADINGS,
    build_plain_text,
    validate_patient_statements,
)
from app.services.patient_identity import age_on, detect_patient_name, validate_temp_personnummer
from app.services.transcript_parser import parse_transcript

MAX_TEMPLATES = 2  # coverage reports per encounter (main symptom first)

STANDARD_WARNINGS = [
    "Prototype output for synthetic / role-played data only: clinician review is required.",
    "Coverage percentages describe transcript evidence against a demo checklist only — not clinician "
    "performance, clinical quality, or standard of care.",
    "Source links show where text appears in the transcript; they do not verify clinical interpretation.",
]


def applied_trigger_concepts(reports: list[CoverageReport], templates: list[ChecklistTemplate]) -> set[str]:
    applied = {r.template_id for r in reports if r.template_id}
    return {c for t in templates if t.template_id in applied for c in t.trigger_concepts}


def not_established_topics(reports: list[CoverageReport], language: str = "en") -> list[str]:
    from app.services.checklist_service import load_registry
    from app.services.patient_explainer import DIMENSION_LABELS_SV

    registry = load_registry()
    topics = []
    for r in reports:
        template = registry.get(r.template_id or "")
        dims = {i.item_id: i.dimension for i in template.items} if template else {}
        for i in r.items:
            if i.status == "not_found_in_transcript":
                dim = dims.get(i.item_id)
                topics.append(DIMENSION_LABELS_SV.get(dim, i.label) if language == "sv" and dim else i.label)
    return list(dict.fromkeys(topics))


def build_patient_explanation(provider: LLMProvider, facts: list[MedicalFact], reports: list[CoverageReport],
                              language: str, patient_name: str | None, date_text: str
                              ) -> tuple[PatientExplanation, list[ValidationFinding]]:
    accepted = [f for f in facts if f.evidence_status == "source_linked"]
    findings: list[ValidationFinding] = []
    statements = []
    # The demo renderer only writes English; Claude writes the requested language.
    out_lang = language if provider.name != "demo" else "en"
    if accepted:
        output = provider.explain_for_patient(accepted, out_lang)
        statements, findings = validate_patient_statements(output, accepted, out_lang)
    not_established = not_established_topics(reports, out_lang)
    lang = "sv" if out_lang == "sv" else "en"
    return PatientExplanation(
        language=out_lang, disclaimer=DISCLAIMERS[lang], intro=INTROS[lang], statements=statements,
        not_established=not_established, section_headings=SECTION_HEADINGS[lang],
        plain_text=build_plain_text(statements, not_established, out_lang, patient_name, date_text),
    ), findings


def build_patient_summary(patient: PatientInfo | None, segments) -> PatientSummary:
    summary = PatientSummary()
    if patient and patient.display_name:
        summary.display_name, summary.name_source = patient.display_name, "entered"
    else:
        detected = detect_patient_name(segments)
        if detected:
            summary.display_name, summary.name_evidence = detected
            summary.name_source = "detected"
    if patient and patient.temp_personnummer:
        pnr, birth = validate_temp_personnummer(patient.temp_personnummer)
        summary.temp_personnummer, summary.birth_date, summary.age = pnr, birth, age_on(birth)
    return summary


def chief_concern_text(note) -> str | None:
    section = next((s for s in note.sections if s.section_id == "chief_concern"), None)
    if section and section.statements:
        return section.statements[0].text.removeprefix("Patient reports ").rstrip(".")
    return None


def run_analysis(transcript: str, templates: list[ChecklistTemplate], provider: LLMProvider,
                 language: str = "en", patient: PatientInfo | None = None) -> AnalyzeResponse:
    parsed = parse_transcript(transcript)
    segments = parsed.segments
    findings: list[ValidationFinding] = []

    extraction = provider.extract(segments, templates) if segments else None
    facts: list[MedicalFact] = []
    rejected: list[MedicalFact] = []
    symptoms = []
    reports: list[CoverageReport] = []

    if extraction is not None:
        facts, rejected, fact_findings = ev.validate_facts(extraction.facts, segments)
        findings += fact_findings
        known_ids = {f.fact_id for f in facts}
        allowed = {t.template_id for t in templates}
        symptoms, sym_findings = ev.validate_symptoms(extraction.symptoms, segments, known_ids, allowed)
        findings += sym_findings

        proposed_ids = {c.template_id for c in extraction.checklist_assessments}
        stray = proposed_ids - allowed
        for tid in sorted(stray):
            findings.append(ValidationFinding(code="unknown_template", severity="error", ref_type="template",
                                              ref_id=tid, message=f"Checklist evidence for unknown template '{tid}' "
                                                                  "was ignored."))
        # A template applies only if a source-linked, patient-mentioned (positive) symptom was mapped to it.
        # Order follows the transcript (main symptom first); at most MAX_TEMPLATES reports.
        applied_ids = list(dict.fromkeys(
            s.template_id for s in symptoms
            if s.template_id and s.evidence_status == "source_linked" and s.polarity == "positive"))[:MAX_TEMPLATES]
        by_id = {t.template_id: t for t in templates}
        for template_id in applied_ids:
            template = by_id[template_id]
            items, cl_findings = ev.validate_checklist(extraction.checklist_assessments, template, segments, known_ids)
            findings += cl_findings
            reports.append(calculate_coverage(template, items))

    if not reports:
        names = ", ".join(t.display_name for t in templates) or "none selected"
        reports.append(no_template_report(
            "Coverage not available: no patient-mentioned symptom in this transcript matched a configured "
            f"checklist template (selected: {names}). TraceCare does not invent checklists."))

    note = generate_clinical_note(facts, reports, applied_trigger_concepts(reports, templates), symptoms)
    patient_summary = build_patient_summary(patient, segments)
    created_at = datetime.now(timezone.utc)
    explanation, pe_findings = build_patient_explanation(provider, facts, reports, language,
                                                         patient_summary.display_name, f"{created_at:%Y-%m-%d}")
    findings += pe_findings

    # Every generated statement must cite known facts (defence in depth for the note renderer).
    known_all = {f.fact_id for f in facts}
    for section in note.sections:
        for s in section.statements:
            bad = ev.unknown_fact_ids(s.fact_ids, known_all)
            if bad:
                raise RuntimeError(f"Note statement {s.statement_id} cites unknown facts {bad}")

    warnings = list(STANDARD_WARNINGS)
    speaker_issues = sum(1 for f in findings if f.code == "speaker_mismatch" or "speaker mismatch" in f.message)
    if speaker_issues >= 2:
        warnings.insert(0, f"{speaker_issues} items show speaker-attribution problems. The transcript's speaker labels "
                           "may be wrong; coverage figures are unreliable until the transcript is corrected and reviewed.")
    if provider.name == "demo":
        warnings.insert(0, "Demo mode: results come from a deterministic rule-based provider, not an AI model.")
        if language == "sv":
            warnings.insert(1, "Swedish patient summaries need the Claude provider; the demo engine wrote English.")
    return AnalyzeResponse(
        encounter_id=str(uuid.uuid4()),
        created_at=created_at,
        provider=provider.name,  # type: ignore[arg-type]
        provider_label=provider.label,
        model=provider.model,
        language=language,
        patient=patient_summary,
        chief_concern=chief_concern_text(note),
        segments=segments,
        facts=facts,
        rejected_facts=rejected,
        symptoms=symptoms,
        coverage_reports=reports,
        clinical_note=note,
        patient_explanation=explanation,
        validation_findings=findings,
        parse_warnings=parsed.warnings,
        warnings=warnings,
    )


def regenerate_after_review(result: AnalyzeResponse, templates: list[ChecklistTemplate]) -> AnalyzeResponse:
    """Recompute the note's follow-up section and overall status after a reviewer override."""
    result.clinical_note = generate_clinical_note(
        result.facts, result.coverage_reports, applied_trigger_concepts(result.coverage_reports, templates),
        result.symptoms)
    pe = result.patient_explanation
    pe.not_established = not_established_topics(result.coverage_reports, pe.language)
    pe.plain_text = build_plain_text(pe.statements, pe.not_established, pe.language, result.patient.display_name,
                                     f"{result.created_at:%Y-%m-%d}")
    reviewed = all(r.review_status == "reviewed" for r in result.coverage_reports if r.items)
    result.status = "reviewed" if reviewed and any(r.items for r in result.coverage_reports) \
        else "provisional_review_required"
    return result
