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
from app.services.patient_explainer import validate_patient_statements
from app.services.patient_identity import age_on, detect_patient_name, validate_temp_personnummer
from app.services.transcript_parser import parse_transcript

STANDARD_WARNINGS = [
    "Prototype output for synthetic / role-played data only: clinician review is required.",
    "Coverage percentages describe transcript evidence against a demo checklist only — not clinician "
    "performance, clinical quality, or standard of care.",
    "Source links show where text appears in the transcript; they do not verify clinical interpretation.",
]


def applied_trigger_concepts(reports: list[CoverageReport], templates: list[ChecklistTemplate]) -> set[str]:
    applied = {r.template_id for r in reports if r.template_id}
    return {c for t in templates if t.template_id in applied for c in t.trigger_concepts}


def build_patient_explanation(provider: LLMProvider, facts: list[MedicalFact], reports: list[CoverageReport],
                              language: str) -> tuple[PatientExplanation, list[ValidationFinding]]:
    accepted = [f for f in facts if f.evidence_status == "source_linked"]
    findings: list[ValidationFinding] = []
    statements = []
    if accepted:
        output = provider.explain_for_patient(accepted, language)
        statements, findings = validate_patient_statements(output, accepted)
    not_established = [i.label for r in reports for i in r.items if i.status == "not_found_in_transcript"]
    return PatientExplanation(language=language, statements=statements, not_established=not_established), findings


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
        # A template applies only if a source-linked, patient-mentioned symptom was mapped to it.
        applied_ids = [s.template_id for s in symptoms if s.template_id and s.evidence_status == "source_linked"]
        for template in templates:
            if template.template_id not in applied_ids:
                continue
            items, cl_findings = ev.validate_checklist(extraction.checklist_assessments, template, segments, known_ids)
            findings += cl_findings
            reports.append(calculate_coverage(template, items))

    if not reports:
        names = ", ".join(t.display_name for t in templates) or "none selected"
        reports.append(no_template_report(
            "Coverage not available: no patient-mentioned symptom in this transcript matched a configured "
            f"checklist template (selected: {names}). TraceCare does not invent checklists."))

    note = generate_clinical_note(facts, reports, applied_trigger_concepts(reports, templates))
    explanation, pe_findings = build_patient_explanation(provider, facts, reports, language)
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
    return AnalyzeResponse(
        encounter_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        provider=provider.name,  # type: ignore[arg-type]
        provider_label=provider.label,
        model=provider.model,
        language=language,
        patient=build_patient_summary(patient, segments),
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
        result.facts, result.coverage_reports, applied_trigger_concepts(result.coverage_reports, templates))
    result.patient_explanation.not_established = [
        i.label for r in result.coverage_reports for i in r.items if i.status == "not_found_in_transcript"]
    reviewed = all(r.review_status == "reviewed" for r in result.coverage_reports if r.items)
    result.status = "reviewed" if reviewed and any(r.items for r in result.coverage_reports) \
        else "provisional_review_required"
    return result
